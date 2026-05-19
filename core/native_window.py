"""Janela nativa embutida — sem abrir navegador externo.
No Windows usa Chrome/Edge em --app mode (janela standalone, sem barra de URL).
Fallback para navegador normal se nenhum browser Chromium for encontrado."""
import logging, subprocess, sys, os, webbrowser


def run_native(url: str, width: int = 480, height: int = 860) -> bool:
    launched = _launch_chromium_app(url, width, height)
    if not launched:
        logging.info("Nenhum Chromium encontrado. Abrindo no navegador.")
        webbrowser.open(url)
    return True


def _launch_chromium_app(url: str, width: int, height: int) -> bool:
    if sys.platform != "win32":
        return False

    browsers = _find_chromium_browsers()
    for exe in browsers:
        try:
            subprocess.Popen(
                [exe, f"--app={url}",
                 f"--window-size={width},{height}",
                 "--disable-extensions",
                 "--disable-default-apps",
                 "--no-first-run"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logging.info(f"Janela nativa aberta via {os.path.basename(exe)}")
            return True
        except (FileNotFoundError, OSError):
            continue
    return False


def _find_chromium_browsers() -> list:
    paths = []
    local = os.environ.get("LOCALAPPDATA", "")
    pf86 = os.environ.get("ProgramFiles(x86)", "")
    pf = os.environ.get("ProgramFiles", "")

    candidates = [
        os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pf, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        os.path.join(local, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(local, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Vivaldi", "Application", "vivaldi.exe"),
        os.path.join(local, "Vivaldi", "Application", "vivaldi.exe"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            paths.append(p)
    return paths
