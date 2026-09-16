from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "Client PSVitaAlive/source/ui/full_catalog_screen.cpp"
LANG_DIR = ROOT / "Client PSVitaAlive/assets/lang"
DOC = ROOT / "Client PSVitaAlive/docs/OLED_PROTECTION_MODE.md"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


cpp = CPP.read_text(encoding="utf-8")

if "kProtectionDelayMs" not in cpp:
    palette_anchor = "unsigned SILVER=RGBA8(0xC8,0xC8,0xCC,255);\n"
    protection_state = r'''

// OLED protection mode for long-running download / extract / install phases.
// It only affects rendering/input; installer, curl, power locks and job control stay untouched.
enum class ProtectionPhase {
    None = 0,
    Downloading,
    Extracting,
    Installing
};

constexpr uint64_t kProtectionDelayMs = 60ULL * 1000ULL;
constexpr uint64_t kProtectionMoveMs = 2ULL * 60ULL * 1000ULL;
constexpr int kProtectionBlockW = 430;
constexpr int kProtectionBlockH = 150;
constexpr int kProtectionMargin = 16;
constexpr int kProtectionMinMoveX = 140;
constexpr int kProtectionMinMoveY = 80;

ProtectionPhase gProtectionPhase = ProtectionPhase::None;
bool gProtectionActive = false;
bool gProtectionTouchConsumeUntilRelease = false;
uint64_t gProtectionPhaseStartMs = 0;
uint64_t gProtectionLastMoveMs = 0;
int gProtectionX = (SCREEN_W - kProtectionBlockW) / 2;
int gProtectionY = (SCREEN_H - kProtectionBlockH) / 2;
uint32_t gProtectionRngState = 0;

uint64_t protectionNowMs() {
    return sceKernelGetProcessTimeWide() / 1000ULL;
}

uint32_t protectionRandom() {
    if (gProtectionRngState == 0) {
        const uint64_t t = sceKernelGetProcessTimeWide();
        gProtectionRngState = static_cast<uint32_t>(t ^ (t >> 32) ^ 0x9E3779B9u);
        if (gProtectionRngState == 0) gProtectionRngState = 0xA341316Cu;
    }
    uint32_t x = gProtectionRngState;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    gProtectionRngState = x ? x : 0xA341316Cu;
    return gProtectionRngState;
}

void protectionChoosePosition(bool forceDifferent) {
    const int minX = kProtectionMargin;
    const int minY = kProtectionMargin;
    const int maxX = SCREEN_W - kProtectionBlockW - kProtectionMargin;
    const int maxY = SCREEN_H - kProtectionBlockH - kProtectionMargin;
    const int spanX = std::max(1, maxX - minX + 1);
    const int spanY = std::max(1, maxY - minY + 1);
    const int oldX = gProtectionX;
    const int oldY = gProtectionY;

    for (int attempt = 0; attempt < 12; ++attempt) {
        const int nx = minX + static_cast<int>(protectionRandom() % static_cast<uint32_t>(spanX));
        const int ny = minY + static_cast<int>(protectionRandom() % static_cast<uint32_t>(spanY));
        const bool movedEnough = std::abs(nx - oldX) >= kProtectionMinMoveX ||
                                 std::abs(ny - oldY) >= kProtectionMinMoveY;
        if (!forceDifferent || movedEnough || attempt == 11) {
            gProtectionX = nx;
            gProtectionY = ny;
            return;
        }
    }
}

ProtectionPhase protectionPhaseForStage(bool active, int outcome, const std::string& stage) {
    if (!active || outcome != 0) return ProtectionPhase::None;

    const bool extracting =
        stage.find("Extract") != std::string::npos ||
        stage.find("extract") != std::string::npos ||
        stage.find("ZIP") != std::string::npos ||
        stage.find("Unzip") != std::string::npos ||
        stage.find("Unpack") != std::string::npos;
    if (extracting) return ProtectionPhase::Extracting;

    const bool installing =
        stage == "Installing" ||
        stage.find("Install") != std::string::npos ||
        stage.find("Promote") != std::string::npos ||
        stage.find("promote") != std::string::npos ||
        stage.find("Converting") != std::string::npos ||
        stage.find("Convert") != std::string::npos ||
        stage.find("ISO") != std::string::npos ||
        stage.find("Finishing") != std::string::npos;
    if (installing) return ProtectionPhase::Installing;

    const bool downloading =
        stage == "Downloading" ||
        stage == "Cancelling" ||
        stage.empty();
    return downloading ? ProtectionPhase::Downloading : ProtectionPhase::None;
}

void protectionUpdateForJob(bool active, int outcome, const std::string& stage) {
    const ProtectionPhase next = protectionPhaseForStage(active, outcome, stage);
    const uint64_t now = protectionNowMs();

    if (next == ProtectionPhase::None) {
        if (gProtectionActive) diagnostics::log("[UI] OLED protection left: job phase ended");
        gProtectionPhase = ProtectionPhase::None;
        gProtectionActive = false;
        gProtectionPhaseStartMs = 0;
        gProtectionLastMoveMs = 0;
        return;
    }

    if (next != gProtectionPhase || gProtectionPhaseStartMs == 0) {
        gProtectionPhase = next;
        gProtectionActive = false;
        gProtectionPhaseStartMs = now;
        gProtectionLastMoveMs = 0;
        protectionChoosePosition(false);
        diagnostics::log("[UI] OLED protection phase timer started");
    }
}

void protectionTick() {
    if (gProtectionPhase == ProtectionPhase::None || gProtectionPhaseStartMs == 0) return;
    const uint64_t now = protectionNowMs();

    if (!gProtectionActive) {
        if (now >= gProtectionPhaseStartMs && (now - gProtectionPhaseStartMs) >= kProtectionDelayMs) {
            gProtectionActive = true;
            protectionChoosePosition(false);
            gProtectionLastMoveMs = now;
            diagnostics::log("[UI] OLED protection entered");
        }
        return;
    }

    if (now >= gProtectionLastMoveMs && (now - gProtectionLastMoveMs) >= kProtectionMoveMs) {
        protectionChoosePosition(true);
        gProtectionLastMoveMs = now;
        diagnostics::log("[UI] OLED protection block moved");
    }
}

void protectionDismiss() {
    if (!gProtectionActive) return;
    gProtectionActive = false;
    gProtectionPhaseStartMs = protectionNowMs();
    gProtectionLastMoveMs = 0;
    diagnostics::log("[UI] OLED protection dismissed by user; grace timer restarted");
}
'''
    cpp = replace_once(cpp, palette_anchor, palette_anchor + protection_state, "protection state")

    progress_anchor = "    installOutcome_ = outcome;\n    installLiveAreaOk_ = liveAreaOk;\n"
    progress_replacement = (
        "    installOutcome_ = outcome;\n"
        "    installLiveAreaOk_ = liveAreaOk;\n"
        "    protectionUpdateForJob(active, outcome, stage);\n"
    )
    cpp = replace_once(cpp, progress_anchor, progress_replacement, "install progress hook")

    input_anchor = "prev=p.buttons;uint32_t nav=direct|repeat;if(themeSetupVisible_)"
    input_replacement = (
        "prev=p.buttons;uint32_t nav=direct|repeat;"
        "if(gProtectionActive&&pressed!=0){protectionDismiss();return;}"
        "if(themeSetupVisible_)"
    )
    cpp = replace_once(cpp, input_anchor, input_replacement, "controller wake hook")

    touch_anchor = '''    SceTouchData td{};\n    if (sceTouchPeek(SCE_TOUCH_PORT_FRONT, &td, 1) <= 0) return;\n\n    // Vita front touch is typically 1920x1088 logical units.\n'''
    touch_replacement = '''    SceTouchData td{};\n    const int touchRet = sceTouchPeek(SCE_TOUCH_PORT_FRONT, &td, 1);\n    if (touchRet <= 0) {\n        if (gProtectionTouchConsumeUntilRelease) gProtectionTouchConsumeUntilRelease = false;\n        return;\n    }\n\n    // A touch may wake the protection screen too, but never leaks into the\n    // underlying download/install controls. Consume until the finger is released.\n    if (gProtectionTouchConsumeUntilRelease) {\n        if (td.reportNum <= 0) gProtectionTouchConsumeUntilRelease = false;\n        return;\n    }\n    if (gProtectionActive) {\n        if (td.reportNum > 0) {\n            protectionDismiss();\n            gProtectionTouchConsumeUntilRelease = true;\n            touchDown_ = false;\n            touchMoved_ = false;\n            touchAccumY_ = 0.f;\n        }\n        return;\n    }\n\n    // Vita front touch is typically 1920x1088 logical units.\n'''
    cpp = replace_once(cpp, touch_anchor, touch_replacement, "touch wake hook")

    draw_anchor = '''    return;\n}\n\n\nconst unsigned RED=RGBA8(0xE0,0x32,0x32,255), GREEN=RGBA8(0x3B,0xD9,0x60,255), BLACK=RGBA8(0,0,0,255);\n'''
    draw_replacement = r'''    return;
}

// Burn-in protection is intentionally restricted to active transfer/extract/install
// phases. The normal progress/result UI returns immediately on phase changes/end.
protectionTick();
if (installProgressActive_ && installOutcome_ == 0 && gProtectionActive) {
    const unsigned protectionBlack = RGBA8(0, 0, 0, 255);
    vita2d_draw_rectangle(0, 0, SCREEN_W, SCREEN_H, protectionBlack);

    using TID = ::psvitaalive::TextId;
    const char* phaseText = ::psvitaalive::L(TID::StageDownloading);
    if (gProtectionPhase == ProtectionPhase::Extracting)
        phaseText = ::psvitaalive::L(TID::StageExtracting);
    else if (gProtectionPhase == ProtectionPhase::Installing)
        phaseText = ::psvitaalive::L(TID::StageInstalling);

    const uint64_t total = installProgressTotal_;
    const uint64_t current = std::min<uint64_t>(installProgressCurrent_, total ? total : installProgressCurrent_);
    const bool determinate = total > 0;
    const uint64_t pct = determinate ? std::min<uint64_t>(100, (current * 100) / total) : 0;
    const bool etaKnown = installProgressSpeed_ > 0 && total > current;
    const uint64_t eta = etaKnown ? (total - current) / installProgressSpeed_ : 0;

    char progressLine[128];
    if (determinate && etaKnown) {
        sceClibSnprintf(progressLine, sizeof(progressLine), "%llu%%   %s: %s",
            (unsigned long long)pct,
            ::psvitaalive::L(TID::LabelEta),
            formatEta(eta).c_str());
    } else if (determinate) {
        sceClibSnprintf(progressLine, sizeof(progressLine), "%llu%%   %s: --",
            (unsigned long long)pct,
            ::psvitaalive::L(TID::LabelEta));
    } else {
        sceClibSnprintf(progressLine, sizeof(progressLine), "--%%   %s: --",
            ::psvitaalive::L(TID::LabelEta));
    }

    auto drawCentered = [&](const char* text, int baselineY, unsigned color, float preferredScale, float minScale) {
        if (!text || !text[0] || !font_) return;
        const int maxWidth = kProtectionBlockW - 24;
        float sc = preferredScale;
        while (sc > minScale && ::psvitaalive::ui::uiTextWidth(&font_, sc, text) > maxWidth)
            sc -= 0.04f;
        if (sc < minScale) sc = minScale;
        const int tw = ::psvitaalive::ui::uiTextWidth(&font_, sc, text);
        ::psvitaalive::ui::uiDrawText(&font_,
            gProtectionX + (kProtectionBlockW - tw) / 2,
            gProtectionY + baselineY,
            color, sc, text);
    };

    // Logical 430x150 block; no panel/border is drawn so the rest remains pure black.
    drawCentered("PSVitaAlive", 24, ACCENT, 0.82f, 0.62f);
    drawCentered(phaseText, 54, TEXT, 0.86f, 0.62f);
    drawCentered(progressLine, 86, ACCENT, 0.82f, 0.58f);
    drawCentered(::psvitaalive::L("PROTECTION_PRESS_ANY_BUTTON"), 126, DIM, 0.64f, 0.46f);
    return;
}

const unsigned RED=RGBA8(0xE0,0x32,0x32,255), GREEN=RGBA8(0x3B,0xD9,0x60,255), BLACK=RGBA8(0,0,0,255);
'''
    cpp = replace_once(cpp, draw_anchor, draw_replacement, "protection renderer")

    CPP.write_text(cpp, encoding="utf-8")

translations = {
    "en.lang": "Press any button to return",
    "es.lang": "Pulsa cualquier botón para volver",
    "fr.lang": "Appuyez sur un bouton pour revenir",
    "de.lang": "Taste drücken zum Zurückkehren",
    "it.lang": "Premi un pulsante per tornare",
    "pt-BR.lang": "Pressione qualquer botão para voltar",
    "pt-PT.lang": "Prima qualquer botão para voltar",
    "ru.lang": "Нажмите любую кнопку, чтобы вернуться",
}

for filename, value in translations.items():
    path = LANG_DIR / filename
    text = path.read_text(encoding="utf-8")
    key = "PROTECTION_PRESS_ANY_BUTTON="
    if key not in text:
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"{key}{value}\n"
        path.write_text(text, encoding="utf-8")

DOC.parent.mkdir(parents=True, exist_ok=True)
DOC.write_text("""# Modo de protección de pantalla (OLED/LCD)\n\n## Objetivo\n\nReducir el tiempo que la interfaz de progreso permanece estática durante descargas, extracciones e instalaciones largas, especialmente en PS Vita 1000 con panel OLED, sin cambiar la política actual de mantener la consola y la pantalla encendidas mientras existe un trabajo activo.\n\nEste sistema es **solo de presentación e input**. No modifica libcurl, el instalador, el extractor, las colas de instalación, los bloqueos del botón PS ni los `sceKernelPowerTick` existentes.\n\n## Comportamiento\n\n- La ventana normal de progreso no se mueve.\n- El temporizador se inicia al entrar en una fase activa reconocida como `Downloading`, extracción o instalación.\n- Tras **60 segundos** en la misma fase aparece el modo de protección.\n- Al cambiar de fase (por ejemplo, Descargando → Extrayendo → Instalando) se restaura inmediatamente la interfaz normal y empieza un nuevo temporizador de 60 segundos.\n- Al finalizar, fallar o cancelar el trabajo, el modo de protección se desactiva inmediatamente y no puede volver a activarse hasta que exista otra fase activa compatible.\n- Si el usuario sale manualmente del protector y la misma fase continúa, se concede un nuevo periodo normal de 60 segundos antes de poder entrar de nuevo.\n\n## Presentación\n\n- Resolución objetivo de PS Vita: **960 × 544**.\n- Fondo del protector: **negro puro** (`#000000`) siempre, independientemente del tema.\n- Bloque lógico de contenido: **430 × 150 px**. No se dibuja panel ni borde alrededor del bloque.\n- El bloque mantiene un margen de seguridad de 16 px respecto a los bordes de la pantalla.\n- El bloque muestra únicamente:\n  - `PSVitaAlive`;\n  - fase actual localizada: Descargando / Extrayendo / Instalando;\n  - porcentaje;\n  - ETA;\n  - mensaje localizado para volver a la interfaz normal.\n- Los colores del texto usan la paleta activa (`ACCENT`, `TEXT`, `DIM`).\n- El render usa `UiFont`, por lo que respeta la fuente/estilo y la escala seleccionados por el usuario.\n\n## Movimiento anti-retención\n\nCada **120 segundos** mientras el modo de protección sigue activo, el bloque se reposiciona de forma pseudoaleatoria dentro del área segura. La selección intenta evitar posiciones demasiado próximas a la anterior (140 px en X o 80 px en Y como distancia mínima útil), manteniendo siempre los 430 × 150 px completamente visibles.\n\n## Input\n\nCualquier pulsación nueva de un botón que llegue al cliente cierra el modo de protección y **consume esa pulsación**. Esto es importante para que Círculo no cancele accidentalmente una descarga al usarse para despertar la interfaz.\n\nEl panel táctil frontal también puede despertar la interfaz. El toque se consume hasta que el dedo se levanta para impedir que llegue a los controles inferiores.\n\n## Multidioma\n\nLos nombres de fase reutilizan los `TextId` existentes (`StageDownloading`, `StageExtracting`, `StageInstalling`). El mensaje del protector utiliza la clave:\n\n```text\nPROTECTION_PRESS_ANY_BUTTON\n```\n\nLa clave se incluye en los paquetes `en`, `es`, `fr`, `de`, `it`, `pt-BR`, `pt-PT` y `ru`.\n\n## Implementación\n\nLa lógica vive en `Client PSVitaAlive/source/ui/full_catalog_screen.cpp` para reutilizar el estado de progreso, tema, fuente, localización e input ya existentes sin introducir un segundo sistema de descarga o instalación.\n\nLos estados principales son:\n\n```text\nFase activa\n   ↓\n60 s en la misma fase\n   ↓\nModo protección\n   ├─ botón/toque → UI normal + nuevo margen de 60 s\n   ├─ 120 s → nueva posición segura\n   ├─ cambio de fase → UI normal + nuevo temporizador\n   └─ fin/error/cancelación → UI/resultados normal, protector desactivado\n```\n\n## Pruebas recomendadas en Vita real\n\n1. Descargar un archivo durante menos de 60 s: el protector no debe aparecer.\n2. Mantener una descarga más de 60 s: debe aparecer con fondo negro, porcentaje y ETA.\n3. Mantener el protector más de 120 s: el bloque debe cambiar de posición sin recortarse.\n4. Pulsar Círculo mientras el protector está activo: debe volver a la UI y **no** cancelar con esa primera pulsación.\n5. Repetir con X, Triángulo, D-Pad y touch.\n6. Verificar una extracción larga y una instalación larga.\n7. Verificar una secuencia Install All: cada cambio de fase debe volver a la UI normal y reiniciar el minuto.\n8. Completar, cancelar y forzar un error: el protector no debe reaparecer después del resultado.\n9. Probar varios temas: el fondo debe seguir negro y solo deben cambiar los colores de texto.\n10. Probar varias fuentes, escalas e idiomas, comprobando que las líneas siguen dentro del bloque de 430 × 150.\n11. Confirmar que la consola continúa con las protecciones actuales de suspensión/apagado durante todo el trabajo.\n\n## Nota\n\nEl modo reduce contenido estático y áreas iluminadas, pero no pretende garantizar la eliminación absoluta de retención o desgaste del panel. Su objetivo es minimizar de forma práctica el riesgo durante operaciones largas sin alterar el funcionamiento del instalador.\n""", encoding="utf-8")

print("OLED protection mode patch applied successfully.")
