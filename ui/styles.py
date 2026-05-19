THEME = {
    "dark": {
        "bg1": "#181825", "bg2": "#1e1e2e", "bg3": "#11111b",
        "txt1": "#cdd6f4", "txt2": "#a6adc8",
        "green": "#a6e3a1", "red": "#f38ba8",
        "yellow": "#f9e2af", "blue": "#89b4fa",
        "border": "#313244"
    }
}
FONTS = {
    "title": ("Segoe UI", 17, "bold"),
    "head": ("Segoe UI", 14, "bold"),
    "body": ("Segoe UI", 13),
    "small": ("Segoe UI", 11)
}
def get(name="dark"):
    return THEME.get(name, THEME["dark"])
