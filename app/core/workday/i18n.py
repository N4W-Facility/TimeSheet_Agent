# ============================================================
# DICCIONARIO DE TRADUCCIONES PARA MULTIIDIOMA
# ============================================================
TRANSLATIONS = {
    "es": {
        "home_marker": "Hola",
        "menu_button_label": "MENÚ",
        "personal_section": "Personal",
        "time_management": "Gestión de tiempo",
        "this_week": "Esta semana",
        "actions": "Acciones",
        "enter_time_by_type": "Introducción de horas por tipo",
        "next_button": "Siguiente",
        "cancel_button": "Cancelar",
        "save_and_close": "Guardar y cerrar",
        "save": "Guardar",
        "next_week": "Siguiente semana",
        "week_label": "Semana",
        "project_label": "Proyecto",
    },
    "en": {
        "home_marker": "Hello",
        "menu_button_label": "MENU",
        "personal_section": "Personal",
        "time_management": "Time",
        "this_week": "This Week",
        "actions": "Actions",
        "enter_time_by_type": "Enter Time by Type",
        "next_button": "Next",
        "cancel_button": "Cancel",
        "save_and_close": "Save and Close",
        "save": "Save",
        "next_week": "Next Week",
        "week_label": "Week",
        "project_label": "Project",
    },
    "pt": {
        "home_marker": "Olá",
        "menu_button_label": "MENU",
        "personal_section": "Pessoal",
        "time_management": "Gestão de Tempo",
        "this_week": "Esta semana",
        "actions": "Ações",
        "enter_time_by_type": "Inserir Horas por Tipo",
        "next_button": "Avançar",
        "cancel_button": "Cancelar",
        "save_and_close": "Salvar e Fechar",
        "save": "Salvar",
        "next_week": "Próxima semana",
        "week_label": "Semana",
        "project_label": "Projeto",
    },
}
def detect_language(labels_text: str) -> str:
    """
    Detecta el idioma comparando textos conocidos del menú de Workday.
    Recibe el texto combinado de los aria-labels del menú.
    """
    if "Gestión de tiempo" in labels_text or "Ausencias" in labels_text:
        return "es"
    elif "Gestão de Tempo" in labels_text or "Ausências" in labels_text:
        return "pt"
    else:
        return "en"
def get_texts(lang: str) -> dict:
    """Retorna el diccionario de textos para el idioma dado."""
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"])