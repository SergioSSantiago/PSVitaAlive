#include "ui/image_cache.hpp"
#include "diagnostic_logger.hpp"
#include "network/http_client.hpp"
#include "storage/storage_manager.hpp"
#include <psp2/kernel/clib.h>
#include <psp2/io/dirent.h>
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#include <png.h>
#include <jpeglib.h>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <setjmp.h>
#include <vector>
namespace psvitaalive::ui { namespace {
constexpr const char* IMAGE_ROOT="ux0:data/psvitaalive/cache/images/v3";
constexpr const char* LEGACY_IMAGE_ROOT="ux0:data/psvitaalive/cache/images/v2";
constexpr const char* IMAGE_MANIFEST_ROOT="ux0:data/psvitaalive/cache/catalog";
constexpr int WORKER_PRIORITY=0x10000100,WORKER_STACK=128*1024,MAX_RETRIES=3;
// Fewer SSL rounds per image — UI should not burn 10× curl-35 on a missing icon.
constexpr int IMAGE_HTTP_ATTEMPTS = 8; // more tries so icon0 lands in cache (no wrong fallback)

/* services/img removed — IA page thumb is often a screenshot, not icon0 */

constexpr uint64_t RETRY_COOLDOWN_US=3000000ULL;
constexpr uint64_t MANIFEST_CHECK_INTERVAL_US=2000000ULL;
constexpr size_t MAX_INTERACTIVE_QUEUE=12;
constexpr unsigned APP_IMAGE_MAX_DIM=128u,SCREENSHOT_IMAGE_MAX_DIM=512u;
unsigned maxImageDimForNamespace(const std::string&ns){return ns=="app"?APP_IMAGE_MAX_DIM:SCREENSHOT_IMAGE_MAX_DIM;}
uint32_t fnv1a(const std::string&v){uint32_t h=2166136261u;for(unsigned char c:v){h^=c;h*=16777619u;}return h;}
uint64_t fnv1a64(const std::string&v){uint64_t h=1469598103934665603ULL;for(unsigned char c:v){h^=c;h*=1099511628211ULL;}return h;}
std::string hex32(uint32_t v){char b[16];sceClibSnprintf(b,sizeof(b),"%08X",v);return b;}
std::string extensionOf(const std::string&u){std::string c=u;size_t q=c.find('?');if(q!=std::string::npos)c.erase(q);size_t f=c.find('#');if(f!=std::string::npos)c.erase(f);size_t d=c.find_last_of('.');if(d==std::string::npos)return".img";std::string e=c.substr(d);for(char&x:e)if(x>='A'&&x<='Z')x=(char)(x-'A'+'a');if(e==".jpeg"||e==".jpg"||e==".png")return".png";return".img";}
std::string normalizeUrl(const std::string&u){if(u.rfind("https://",0)==0||u.rfind("http://",0)==0)return u;std::string p=u;while(p.rfind("../",0)==0)p.erase(0,3);return std::string("https://raw.githubusercontent.com/VegettoSan/PSVitaAlive/main/")+p;}

struct TaggedImageUrl{std::string url;std::string catalogPrefix;};
bool validCatalogPrefix(const std::string&p){return p=="H"||p=="PV"||p=="PSP"||p=="PS1";}
TaggedImageUrl splitCatalogTag(const std::string&tagged){
    TaggedImageUrl out{tagged,"U"};
    const std::string hashMarker="#psva_cat=";
    const std::string ampMarker="&psva_cat=";
    const size_t hp=tagged.rfind(hashMarker),ap=tagged.rfind(ampMarker);
    size_t pos=std::string::npos,markerLen=0;
    if(hp!=std::string::npos&&(ap==std::string::npos||hp>ap)){pos=hp;markerLen=hashMarker.size();}
    else if(ap!=std::string::npos){pos=ap;markerLen=ampMarker.size();}
    if(pos==std::string::npos)return out;
    const std::string prefix=tagged.substr(pos+markerLen);
    if(!validCatalogPrefix(prefix))return out;
    out.url=tagged.substr(0,pos);
    out.catalogPrefix=prefix;
    return out;
}
std::string manifestPathForPrefix(const std::string&prefix){return std::string(IMAGE_MANIFEST_ROOT)+"/images_"+prefix+".manifest";}
std::string baseNameOf(const std::string&path){const size_t slash=path.find_last_of('/');return slash==std::string::npos?path:path.substr(slash+1);}
bool endsWith(const std::string&value,const char*suffix){if(!suffix)return false;const size_t n=std::strlen(suffix);return value.size()>=n&&value.compare(value.size()-n,n,suffix)==0;}
bool cacheFileBelongsToCatalog(const std::string&name,const std::string&catalogPrefix){
    // v3 format: <namespace>_<catalog>_<urlhash>.<ext>, e.g. app_H_12AB34CD.png.
    // Keeping namespace first preserves existing UI checks for /app_ and /shot_.
    const size_t first=name.find('_');if(first==std::string::npos)return false;
    const size_t second=name.find('_',first+1);if(second==std::string::npos)return false;
    return name.compare(first+1,second-first-1,catalogPrefix)==0&&catalogPrefix.size()==second-first-1;
}
bool removeTreeRecursive(const std::string&path,uint32_t*files,uint64_t*bytes){
    SceUID fd=sceIoDopen(path.c_str());
    if(fd<0)return false;
    SceIoDirent ent;
    while(sceIoDread(fd,&ent)>0){
        if(std::strcmp(ent.d_name,".")==0||std::strcmp(ent.d_name,"..")==0)continue;
        const std::string child=path+"/"+ent.d_name;
        if(SCE_S_ISDIR(ent.d_stat.st_mode))removeTreeRecursive(child,files,bytes);
        else if(sceIoRemove(child.c_str())>=0){if(files)++(*files);if(bytes&&ent.d_stat.st_size>0)*bytes+=(uint64_t)ent.d_stat.st_size;}
    }
    sceIoDclose(fd);
    sceIoRmdir(path.c_str());
    return true;
}
bool readMagic(const std::string&path,unsigned char*magic,size_t n){FILE*f=std::fopen(path.c_str(),"rb");if(!f)return false;size_t got=std::fread(magic,1,n,f);std::fclose(f);return got==n;}
bool cachedNormalizedPngLooksValid(const std::string&path,unsigned maxDim){unsigned char hdr[24]={};FILE*f=std::fopen(path.c_str(),"rb");if(!f)return false;size_t got=std::fread(hdr,1,sizeof(hdr),f);std::fclose(f);if(got!=sizeof(hdr))return false;static const unsigned char sig[8]={0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A};if(std::memcmp(hdr,sig,sizeof(sig))!=0||std::memcmp(hdr+12,"IHDR",4)!=0)return false;auto be32=[](const unsigned char*p)->unsigned{return ((unsigned)p[0]<<24)|((unsigned)p[1]<<16)|((unsigned)p[2]<<8)|(unsigned)p[3];};unsigned w=be32(hdr+16),h=be32(hdr+20);return w>0&&h>0&&(maxDim==0||(w<=maxDim&&h<=maxDim));}
bool normalizePngForVita(const std::string&path,unsigned maxDim){png_image image{};image.version=PNG_IMAGE_VERSION;if(!png_image_begin_read_from_file(&image,path.c_str()))return false;if(image.width==0||image.height==0||image.width>2048||image.height>2048){png_image_free(&image);return false;}image.format=PNG_FORMAT_RGBA;size_t bytes=PNG_IMAGE_SIZE(image);if(bytes==0){png_image_free(&image);return false;}std::vector<unsigned char>pixels(bytes);if(!png_image_finish_read(&image,nullptr,pixels.data(),0,nullptr)){png_image_free(&image);return false;}unsigned srcW=image.width,srcH=image.height,dstW=srcW,dstH=srcH;if(maxDim>0&&(srcW>maxDim||srcH>maxDim)){double scale=std::min((double)maxDim/(double)srcW,(double)maxDim/(double)srcH);dstW=std::max(1u,(unsigned)(srcW*scale+0.5));dstH=std::max(1u,(unsigned)(srcH*scale+0.5));}std::vector<unsigned char>outPixels((size_t)dstW*dstH*4);for(unsigned y=0;y<dstH;++y){unsigned sy=(unsigned)((uint64_t)y*srcH/dstH);for(unsigned x=0;x<dstW;++x){unsigned sx=(unsigned)((uint64_t)x*srcW/dstW);const unsigned char*src=&pixels[((size_t)sy*srcW+sx)*4];unsigned char*dst=&outPixels[((size_t)y*dstW+x)*4];dst[0]=src[0];dst[1]=src[1];dst[2]=src[2];dst[3]=src[3];}}std::string temp=path+".normalized";png_image output{};output.version=PNG_IMAGE_VERSION;output.width=dstW;output.height=dstH;output.format=PNG_FORMAT_RGBA;if(!png_image_write_to_file(&output,temp.c_str(),0,outPixels.data(),0,nullptr)){png_image_free(&image);png_image_free(&output);sceIoRemove(temp.c_str());return false;}png_image_free(&image);png_image_free(&output);sceIoRemove(path.c_str());if(sceIoRename(temp.c_str(),path.c_str())<0){sceIoRemove(temp.c_str());return false;}return true;}
struct JpegError{jpeg_error_mgr pub;jmp_buf jump;};
void jpegErrorExit(j_common_ptr c){JpegError*e=reinterpret_cast<JpegError*>(c->err);longjmp(e->jump,1);}
bool normalizeJpegForVita(const std::string&path,unsigned maxDim){FILE*in=std::fopen(path.c_str(),"rb");if(!in)return false;jpeg_decompress_struct cinfo{};JpegError jerr{};cinfo.err=jpeg_std_error(&jerr.pub);jerr.pub.error_exit=jpegErrorExit;if(setjmp(jerr.jump)){jpeg_destroy_decompress(&cinfo);std::fclose(in);return false;}jpeg_create_decompress(&cinfo);jpeg_stdio_src(&cinfo,in);jpeg_read_header(&cinfo,TRUE);cinfo.out_color_space=JCS_RGB;jpeg_start_decompress(&cinfo);if(cinfo.output_width==0||cinfo.output_height==0||cinfo.output_width>2048||cinfo.output_height>2048){jpeg_abort_decompress(&cinfo);jpeg_destroy_decompress(&cinfo);std::fclose(in);return false;}size_t rowBytes=(size_t)cinfo.output_width*3;std::vector<unsigned char>pixels(rowBytes*(size_t)cinfo.output_height);while(cinfo.output_scanline<cinfo.output_height){JSAMPROW row=pixels.data()+(size_t)cinfo.output_scanline*rowBytes;jpeg_read_scanlines(&cinfo,&row,1);}unsigned w=cinfo.output_width,h=cinfo.output_height;jpeg_finish_decompress(&cinfo);jpeg_destroy_decompress(&cinfo);std::fclose(in);unsigned dw=w,dh=h;if(maxDim>0&&(w>maxDim||h>maxDim)){double scale=std::min((double)maxDim/(double)w,(double)maxDim/(double)h);dw=std::max(1u,(unsigned)(w*scale+0.5));dh=std::max(1u,(unsigned)(h*scale+0.5));}std::vector<unsigned char>outPixels((size_t)dw*dh*3);for(unsigned y=0;y<dh;++y){unsigned sy=(unsigned)((uint64_t)y*h/dh);for(unsigned x=0;x<dw;++x){unsigned sx=(unsigned)((uint64_t)x*w/dw);const unsigned char*src=&pixels[((size_t)sy*w+sx)*3];unsigned char*dst=&outPixels[((size_t)y*dw+x)*3];dst[0]=src[0];dst[1]=src[1];dst[2]=src[2];}}std::string temp=path+".normalized";png_image out{};out.version=PNG_IMAGE_VERSION;out.width=dw;out.height=dh;out.format=PNG_FORMAT_RGB;if(!png_image_write_to_file(&out,temp.c_str(),0,outPixels.data(),0,nullptr)){sceIoRemove(temp.c_str());return false;}sceIoRemove(path.c_str());if(sceIoRename(temp.c_str(),path.c_str())<0){sceIoRemove(temp.c_str());return false;}return true;}
bool normalizeImageForVita(const std::string&path,unsigned maxDim){unsigned char magic[12]={};if(!readMagic(path,magic,sizeof(magic)))return false;bool png=magic[0]==0x89&&magic[1]==0x50&&magic[2]==0x4E&&magic[3]==0x47&&magic[4]==0x0D&&magic[5]==0x0A&&magic[6]==0x1A&&magic[7]==0x0A;bool jpg=magic[0]==0xFF&&magic[1]==0xD8&&magic[2]==0xFF;if(png)return normalizePngForVita(path,maxDim);if(jpg)return normalizeJpegForVita(path,maxDim);return false;}
}
ImageCache::ImageCache()=default;ImageCache::~ImageCache(){shutdown();}
bool ImageCache::ensureDirectory(const std::string&p)const{StorageManager s;return s.createDirectories(p);}
bool ImageCache::init(){
    if(workerThread_>=0)return true;
    SceIoStat legacyStat={};
    if(sceIoGetstat(LEGACY_IMAGE_ROOT,&legacyStat)>=0&&SCE_S_ISDIR(legacyStat.st_mode)){
        uint32_t files=0;uint64_t bytes=0;
        removeTreeRecursive(LEGACY_IMAGE_ROOT,&files,&bytes);
        char m[180];sceClibSnprintf(m,sizeof(m),"[ImageCache] migrated cache v2->v3 removed=%u freed=%llu",(unsigned)files,(unsigned long long)bytes);diagnostics::log(m);
    }
    if(!ensureDirectory(IMAGE_ROOT))return false;
    ensureDirectory("ux0:data/psvitaalive/logs");
    mutex_=sceKernelCreateMutex("PSVitaAliveImageCache",0,0,nullptr);if(mutex_<0)return false;stopping_=false;cancelRequested_=false;workerThread_=sceKernelCreateThread("PSVitaAliveImageWorker",&ImageCache::workerEntry,WORKER_PRIORITY,WORKER_STACK,0,0,nullptr);if(workerThread_<0){sceKernelDeleteMutex(mutex_);mutex_=-1;return false;}ImageCache*self=this;int r=sceKernelStartThread(workerThread_,sizeof(self),&self);if(r<0){sceKernelDeleteThread(workerThread_);workerThread_=-1;sceKernelDeleteMutex(mutex_);mutex_=-1;return false;}diagnostics::log("[ImageCache] worker initialized cache=v3 catalog-prefixes=H,PV,PSP,PS1");return true;
}
void ImageCache::shutdown(){stopping_=true;cancelRequested_=true;if(workerThread_>=0){sceKernelWaitThreadEnd(workerThread_,nullptr,nullptr);sceKernelDeleteThread(workerThread_);workerThread_=-1;}if(mutex_>=0){sceKernelDeleteMutex(mutex_);mutex_=-1;}queue_.clear();pending_.clear();ready_.clear();failed_.clear();retryAfter_.clear();manifestRevision_.clear();manifestCheckAfter_.clear();currentFile_.clear();currentPath_.clear();currentDownloaded_=0;currentTotal_=0;currentSpeed_=0;diagnostics::log("[ImageCache] shutdown");}
bool ImageCache::contains(const std::vector<std::string>&v,const std::string&s)const{return std::find(v.begin(),v.end(),s)!=v.end();}
std::string ImageCache::makePath(const std::string&url,const std::string&ns)const{const TaggedImageUrl tagged=splitCatalogTag(url);const std::string clean=normalizeUrl(tagged.url);const std::string imageNs=ns.empty()?"misc":ns;return std::string(IMAGE_ROOT)+"/"+imageNs+"_"+tagged.catalogPrefix+"_"+hex32(fnv1a(clean))+extensionOf(clean);}
std::string ImageCache::pathFor(const std::string& url, const std::string& namespaceName) const {
    if (url.empty()) return {};
    return makePath(url, namespaceName);
}

void ImageCache::pruneCatalogIfNeeded(const std::string&catalogPrefix){
    if(!validCatalogPrefix(catalogPrefix)||mutex_<0)return;
    const uint64_t now=sceKernelGetSystemTimeWide();
    uint64_t previousRevision=0;
    sceKernelLockMutex(mutex_,1,nullptr);
    const auto ci=manifestCheckAfter_.find(catalogPrefix);
    if(ci!=manifestCheckAfter_.end()&&now<ci->second){sceKernelUnlockMutex(mutex_,1);return;}
    manifestCheckAfter_[catalogPrefix]=now+MANIFEST_CHECK_INTERVAL_US;
    const auto ri=manifestRevision_.find(catalogPrefix);if(ri!=manifestRevision_.end())previousRevision=ri->second;
    sceKernelUnlockMutex(mutex_,1);

    const std::string manifestPath=manifestPathForPrefix(catalogPrefix);
    FILE*f=std::fopen(manifestPath.c_str(),"rb");if(!f)return;
    char line[4096]={};
    if(!std::fgets(line,sizeof(line),f)||std::strncmp(line,"PSVAIMG1 ",9)!=0){std::fclose(f);return;}
    char*end=nullptr;const uint64_t revision=(uint64_t)std::strtoull(line+9,&end,10);
    if(revision==0){std::fclose(f);return;}
    if(revision==previousRevision){std::fclose(f);return;}

    std::vector<uint64_t>keep;
    while(std::fgets(line,sizeof(line),f)){
        size_t len=std::strlen(line);while(len>0&&(line[len-1]==10||line[len-1]==13))line[--len]=0;
        char*tab=std::strchr(line,9);if(!tab)continue;*tab=0;const char*ns=line;const char*url=tab+1;if(!*ns||!*url)continue;
        const std::string path=makePath(url,ns);keep.push_back(fnv1a64(baseNameOf(path)));
    }
    std::fclose(f);
    std::sort(keep.begin(),keep.end());keep.erase(std::unique(keep.begin(),keep.end()),keep.end());

    std::vector<uint64_t>protectedKeys;
    sceKernelLockMutex(mutex_,1,nullptr);
    if(!currentPath_.empty())protectedKeys.push_back(fnv1a64(baseNameOf(currentPath_)));
    for(const Job&j:queue_)protectedKeys.push_back(fnv1a64(baseNameOf(j.path)));
    for(const std::string&p:pending_)protectedKeys.push_back(fnv1a64(baseNameOf(p)));
    sceKernelUnlockMutex(mutex_,1);
    std::sort(protectedKeys.begin(),protectedKeys.end());protectedKeys.erase(std::unique(protectedKeys.begin(),protectedKeys.end()),protectedKeys.end());

    std::vector<std::string>removedPaths;
    uint64_t freed=0;bool deferred=false;bool scanOk=false;
    SceUID dir=sceIoDopen(IMAGE_ROOT);
    if(dir>=0){
        scanOk=true;SceIoDirent ent;
        while(sceIoDread(dir,&ent)>0){
            if(std::strcmp(ent.d_name,".")==0||std::strcmp(ent.d_name,"..")==0||SCE_S_ISDIR(ent.d_stat.st_mode))continue;
            const std::string name=ent.d_name;
            if(!cacheFileBelongsToCatalog(name,catalogPrefix)||endsWith(name,".normalized"))continue;
            const uint64_t key=fnv1a64(name);
            if(std::binary_search(keep.begin(),keep.end(),key))continue;
            if(std::binary_search(protectedKeys.begin(),protectedKeys.end(),key)){deferred=true;continue;}
            const std::string full=std::string(IMAGE_ROOT)+"/"+name;
            if(sceIoRemove(full.c_str())>=0){removedPaths.push_back(full);if(ent.d_stat.st_size>0)freed+=(uint64_t)ent.d_stat.st_size;}
            else deferred=true;
        }
        sceIoDclose(dir);
    }
    if(!scanOk)return;

    sceKernelLockMutex(mutex_,1,nullptr);
    for(const std::string&p:removedPaths){
        ready_.erase(std::remove(ready_.begin(),ready_.end(),p),ready_.end());
        failed_.erase(std::remove(failed_.begin(),failed_.end(),p),failed_.end());
        pending_.erase(std::remove(pending_.begin(),pending_.end(),p),pending_.end());
        retryAfter_.erase(p);
    }
    if(!deferred)manifestRevision_[catalogPrefix]=revision;
    sceKernelUnlockMutex(mutex_,1);

    if(!removedPaths.empty()||deferred){char m[220];sceClibSnprintf(m,sizeof(m),"[ImageCache] catalog cleanup prefix=%s removed=%u freed=%llu deferred=%d",catalogPrefix.c_str(),(unsigned)removedPaths.size(),(unsigned long long)freed,deferred?1:0);diagnostics::log(m);}
}

void ImageCache::cancelQueuedExcept(const std::unordered_set<std::string>& keep) {
    if (mutex_ < 0) return;
    sceKernelLockMutex(mutex_, 1, nullptr);
    size_t removed = 0;
    std::vector<Job> keptJobs;
    keptJobs.reserve(queue_.size());
    for (const Job& j : queue_) {
        if (keep.find(j.path) != keep.end()) {
            keptJobs.push_back(j);
        } else {
            pending_.erase(std::remove(pending_.begin(), pending_.end(), j.path), pending_.end());
            ++removed;
        }
    }
    queue_.swap(keptJobs);
    sceKernelUnlockMutex(mutex_, 1);
    if (removed > 0) {
        char m[128];
        sceClibSnprintf(m, sizeof(m), "[ImageCache] pruned %u off-screen queued downloads", (unsigned)removed);
        diagnostics::log(m);
    }
}

std::string ImageCache::request(const std::string&url,const std::string&ns){if(url.empty()||mutex_<0)return{};const TaggedImageUrl tagged=splitCatalogTag(url);pruneCatalogIfNeeded(tagged.catalogPrefix);std::string full=normalizeUrl(tagged.url),path=makePath(url,ns);const uint64_t now=sceKernelGetSystemTimeWide();sceKernelLockMutex(mutex_,1,nullptr);if(contains(ready_,path)||contains(pending_,path)){sceKernelUnlockMutex(mutex_,1);return path;}if(contains(failed_,path)){auto it=retryAfter_.find(path);if(it!=retryAfter_.end()&&now<it->second){sceKernelUnlockMutex(mutex_,1);return path;}failed_.erase(std::remove(failed_.begin(),failed_.end(),path),failed_.end());retryAfter_[path]=now+RETRY_COOLDOWN_US;queue_.push_back({full,path,0});pending_.push_back(path);sceKernelUnlockMutex(mutex_,1);return path;}sceKernelUnlockMutex(mutex_,1);SceIoStat st={};if(sceIoGetstat(path.c_str(),&st)>=0&&st.st_size>0){bool validCached=cachedNormalizedPngLooksValid(path,maxImageDimForNamespace(ns));if(validCached){sceKernelLockMutex(mutex_,1,nullptr);if(!contains(ready_,path))ready_.push_back(path);retryAfter_.erase(path);sceKernelUnlockMutex(mutex_,1);return path;}sceIoRemove(path.c_str());}sceKernelLockMutex(mutex_,1,nullptr);bool queued=std::any_of(queue_.begin(),queue_.end(),[&](const Job&j){return j.path==path;});if(!queued&&!contains(pending_,path)){if(!bulkPreload_&&queue_.size()>=MAX_INTERACTIVE_QUEUE){const Job dropped=queue_.back();queue_.pop_back();pending_.erase(std::remove(pending_.begin(),pending_.end(),dropped.path),pending_.end());diagnostics::log(std::string("[ImageCache] dropped stale queued request path=")+dropped.path);}pending_.push_back(path);if(bulkPreload_)queue_.push_back({full,path,0});else queue_.insert(queue_.begin(),{full,path,0});}sceKernelUnlockMutex(mutex_,1);return path;}
void ImageCache::preload(const std::vector<std::string>&urls,const std::string&ns){if(mutex_<0||urls.empty())return;sceKernelLockMutex(mutex_,1,nullptr);bulkPreload_=true;sceKernelUnlockMutex(mutex_,1);size_t queued=0;for(const auto&url:urls){if(url.empty())continue;std::string before=request(url,ns);if(!before.empty())++queued;}sceKernelLockMutex(mutex_,1,nullptr);bulkPreload_=false;sceKernelUnlockMutex(mutex_,1);if(queued){char m[160];sceClibSnprintf(m,sizeof(m),"[ImageCache] preload requested ns=%s count=%u",ns.c_str(),(unsigned)queued);diagnostics::log(m);}}
bool ImageCache::isReady(const std::string&p)const{if(p.empty()||mutex_<0)return false;sceKernelLockMutex(mutex_,1,nullptr);bool r=contains(ready_,p);sceKernelUnlockMutex(mutex_,1);return r;}
bool ImageCache::isFailed(const std::string&p)const{if(mutex_<0||p.empty())return false;sceKernelLockMutex(mutex_,1,nullptr);bool r=contains(failed_,p);sceKernelUnlockMutex(mutex_,1);return r;}
bool ImageCache::isPending(const std::string& localPath) const {
    if (mutex_ < 0 || localPath.empty()) return false;
    sceKernelLockMutex(mutex_, 1, nullptr);
    const bool pending = contains(pending_, localPath) || currentPath_ == localPath;
    sceKernelUnlockMutex(mutex_, 1);
    return pending;
}

bool ImageCache::isCached(const std::string&url,const std::string&ns)const{if(mutex_<0||url.empty())return false;const std::string path=makePath(url,ns);SceIoStat st={};return sceIoGetstat(path.c_str(),&st)>=0&&st.st_size>0;}
ImageCache::ProgressSnapshot ImageCache::progress()const{
    ProgressSnapshot s;
    if(mutex_<0)return s;
    sceKernelLockMutex(mutex_,1,nullptr);
    s.active=!currentPath_.empty();
    s.downloaded=currentDownloaded_;
    s.total=currentTotal_;
    s.speed=currentSpeed_;
    s.completedBytes=completedBytes_;
    s.knownTotalBytes=completedTotalBytes_;
    if(s.active&&s.total>0)s.knownTotalBytes+=s.total;
    s.fileName=currentFile_;
    s.localPath=currentPath_;
    sceKernelUnlockMutex(mutex_,1);
    return s;
}
void ImageCache::resetProgress(){if(mutex_<0)return;sceKernelLockMutex(mutex_,1,nullptr);completedBytes_=0;completedTotalBytes_=0;currentDownloaded_=0;currentTotal_=0;currentSpeed_=0;currentFile_.clear();currentPath_.clear();sceKernelUnlockMutex(mutex_,1);}
void ImageCache::cancelAll(){if(mutex_<0)return;sceKernelLockMutex(mutex_,1,nullptr);const bool active=!currentPath_.empty();const size_t queued=queue_.size();for(const Job&j:queue_)pending_.erase(std::remove(pending_.begin(),pending_.end(),j.path),pending_.end());queue_.clear();cancelRequested_=active;sceKernelUnlockMutex(mutex_,1);if(queued||active)diagnostics::log("[ImageCache] cancel requested for image work");}
void ImageCache::cancelQueuedRequests(){if(mutex_<0)return;sceKernelLockMutex(mutex_,1,nullptr);std::vector<std::string>cancelled;cancelled.reserve(queue_.size());for(const Job&j:queue_)cancelled.push_back(j.path);const size_t count=queue_.size();queue_.clear();for(const auto&p:cancelled)pending_.erase(std::remove(pending_.begin(),pending_.end(),p),pending_.end());sceKernelUnlockMutex(mutex_,1);if(count){char m[160];sceClibSnprintf(m,sizeof(m),"[ImageCache] cancelled queued requests=%u",(unsigned)count);diagnostics::log(m);}}
void ImageCache::markReady(const std::string&p){sceKernelLockMutex(mutex_,1,nullptr);if(!contains(ready_,p))ready_.push_back(p);pending_.erase(std::remove(pending_.begin(),pending_.end(),p),pending_.end());failed_.erase(std::remove(failed_.begin(),failed_.end(),p),failed_.end());retryAfter_.erase(p);sceKernelUnlockMutex(mutex_,1);}
void ImageCache::markFailed(const std::string&p){sceKernelLockMutex(mutex_,1,nullptr);pending_.erase(std::remove(pending_.begin(),pending_.end(),p),pending_.end());if(!contains(failed_,p))failed_.push_back(p);retryAfter_[p]=sceKernelGetSystemTimeWide()+RETRY_COOLDOWN_US;sceKernelUnlockMutex(mutex_,1);}
int ImageCache::workerEntry(SceSize a,void*arg){(void)a;ImageCache*self=nullptr;if(arg)std::memcpy(&self,arg,sizeof(self));return self?self->workerMain():-1;}
void ImageCache::setNetworkPaused(bool paused){if(mutex_>=0)sceKernelLockMutex(mutex_,1,nullptr);const bool changed=(networkPaused_!=paused);networkPaused_=paused;if(mutex_>=0)sceKernelUnlockMutex(mutex_,1);if(changed){if(paused)diagnostics::log("[ImageCache] network paused (install/download active)");else diagnostics::log("[ImageCache] network resumed");}}int ImageCache::workerMain(){HttpClient http;if(http.init()!=HttpResult::Ok){diagnostics::log("[ImageCache] HTTP initialization failed");return-1;}while(!stopping_){bool paused=false;if(mutex_>=0){sceKernelLockMutex(mutex_,1,nullptr);paused=networkPaused_;sceKernelUnlockMutex(mutex_,1);}if(paused){sceKernelDelayThread(100*1000);continue;}Job job;bool have=false;sceKernelLockMutex(mutex_,1,nullptr);if(!queue_.empty()){job=queue_.front();queue_.erase(queue_.begin());have=true;const size_t slash=job.url.find_last_of('/');currentFile_=(slash==std::string::npos?job.url:job.url.substr(slash+1));currentPath_=job.path;currentDownloaded_=0;currentTotal_=0;currentSpeed_=0;}sceKernelUnlockMutex(mutex_,1);if(!have){sceKernelDelayThread(50*1000);continue;}HttpProgressFn onProgress=[this](const HttpProgress&p){if(mutex_<0)return;sceKernelLockMutex(mutex_,1,nullptr);currentDownloaded_=p.downloaded;currentTotal_=p.total;currentSpeed_=p.bytesPerSecond;sceKernelUnlockMutex(mutex_,1);};HttpCancelFn shouldCancel=[this](){if(mutex_<0)return true;sceKernelLockMutex(mutex_,1,nullptr);const bool c=cancelRequested_||stopping_;sceKernelUnlockMutex(mutex_,1);return c;};/* A: only real catalog URL (icon0/shots). B: IMAGE_HTTP_ATTEMPTS retries to fill cache. */HttpResult r=http.downloadToFile(job.url,job.path,0,onProgress,shouldCancel,IMAGE_HTTP_ATTEMPTS);if(job.url.find("archive.org")!=std::string::npos){/* archive.org image spacing */sceKernelDelayThread(150*1000);}sceKernelLockMutex(mutex_,1,nullptr);const bool cancelled=cancelRequested_||r==HttpResult::Cancelled;const uint64_t doneBytes=currentDownloaded_,doneTotal=currentTotal_;if(!cancelled&&r==HttpResult::Ok){completedBytes_+=doneBytes;if(doneTotal>0)completedTotalBytes_+=doneTotal;}currentFile_.clear();currentPath_.clear();currentDownloaded_=0;currentTotal_=0;currentSpeed_=0;cancelRequested_=false;sceKernelUnlockMutex(mutex_,1);if(cancelled){sceIoRemove(job.path.c_str());sceKernelLockMutex(mutex_,1,nullptr);pending_.erase(std::remove(pending_.begin(),pending_.end(),job.path),pending_.end());sceKernelUnlockMutex(mutex_,1);diagnostics::log(std::string("[ImageCache] cancelled url=")+job.url+" path="+job.path);continue;}bool valid=false;if(r==HttpResult::Ok){SceIoStat st={};valid=sceIoGetstat(job.path.c_str(),&st)>=0&&st.st_size>0;}const uint64_t normStart=sceKernelGetSystemTimeWide();if(valid)valid=normalizeImageForVita(job.path,job.path.find("/app_")!=std::string::npos?APP_IMAGE_MAX_DIM:SCREENSHOT_IMAGE_MAX_DIM);const uint64_t normUs=sceKernelGetSystemTimeWide()-normStart;if(valid&&normUs>=8000ULL){char pm[220];sceClibSnprintf(pm,sizeof(pm),"[Perf] image normalize slow us=%llu path=%s",(unsigned long long)normUs,job.path.c_str());diagnostics::log(pm);}if(valid){markReady(job.path);char m[900];sceClibSnprintf(m,sizeof(m),"[ImageCache] ready url=%s path=%s attempt=%d",job.url.c_str(),job.path.c_str(),job.attempt+1);diagnostics::log(m);}else{sceIoRemove(job.path.c_str());char m[1000];sceClibSnprintf(m,sizeof(m),"[ImageCache] failed url=%s path=%s attempt=%d http=%d error=%s",job.url.c_str(),job.path.c_str(),job.attempt+1,http.lastStatusCode(),http.lastError().c_str());diagnostics::log(m);if(job.attempt+1<MAX_RETRIES&&!stopping_){sceKernelDelayThread((job.attempt+1)*250*1000);job.attempt++;sceKernelLockMutex(mutex_,1,nullptr);queue_.push_back(job);sceKernelUnlockMutex(mutex_,1);}else markFailed(job.path);}}http.shutdown();return 0;}
} // namespace psvitaalive::ui
