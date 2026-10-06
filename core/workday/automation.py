# ============================================================
# AUTOMATIZACIÓN DE WORKDAY CON PLAYWRIGHT
# Selectores basados en data-automation-id (independiente del idioma)
# ============================================================
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from config import TIMEOUT, MAX_RETRIES, CDP_URL
from core.workday.i18n import detect_language, get_texts
from core.workday.csv_reader import get_week_dates, format_hours
class WorkdayAutomation:
    def __init__(self, log_callback=None, confirm_callback=None):
        self.playwright = None
        self.browser = None
        self.page = None
        self.texts = None
        self.lang = None
        self.log = log_callback if log_callback else print
        self.confirm = confirm_callback if confirm_callback else lambda msg: True
    def connect(self):
        """Se conecta al navegador ya abierto vía CDP."""
        self.log("Conectando al navegador...")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.connect_over_cdp(CDP_URL)
        context = self.browser.contexts[0]
        self.page = context.pages[0]
        self.page.set_default_timeout(TIMEOUT)
        self.log("✓ Conectado al navegador")
    def detect_lang(self):
        """
        Detecta el idioma leyendo el aria-label del primer link del menú.
        Método robusto que no depende del contenido general de la página.
        """
        self.lang = "es"
        '''
        # Abrir el menú para leer los links
        self.page.locator('[data-automation-id="globalNavButton"]').click()
        self.page.wait_for_timeout(1200)
        # Leer el aria-label del primer link disponible en el menú
        links = self.page.locator('[data-automation-id="globalNavAppItemLink"]').all()
        all_labels = []
        for link in links:
            label = link.get_attribute("aria-label") or link.inner_text()
            all_labels.append(label.strip())
        # Cerrar el menú
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(500)
        self.log(f"  Links encontrados: {all_labels}")
        # Detectar idioma comparando con los textos conocidos de cada idioma
        combined = " ".join(all_labels)
        if "Gestión de tiempo" in combined or "Ausencias" in combined:
            self.lang = "es"
        elif "Gestão de Tempo" in combined or "Ausências" in combined:
            self.lang = "pt"
        else:
            self.lang = "en"
        '''
        self.texts = get_texts(self.lang)
        self.log(f"✓ Idioma detectado: {self.lang.upper()}")
    def navigate_to_time_management(self):
        """
        Navega a Gestión de tiempo desde el menú principal.
        Usa aria-label que es independiente del renderizado visual.
        """
        t = self.texts
        # Abrir menú
        self.log("Abriendo menú principal...")
        self.page.locator('[data-automation-id="globalNavButton"]').click()
        self.page.wait_for_timeout(1200)
        # Buscar el link por aria-label exacto en el idioma detectado
        self.log(f"Buscando '{t['time_management']}'...")
        time_link = self.page.locator(
            f'[data-automation-id="globalNavAppItemLink"][aria-label="{t["time_management"]}"]'
        )
        count = time_link.count()
        self.log(f"  Links encontrados con ese aria-label: {count}")
        if count == 0:
            # Fallback: iterar todos los links y comparar texto
            all_links = self.page.locator('[data-automation-id="globalNavAppItemLink"]').all()
            for link in all_links:
                label = link.get_attribute("aria-label") or link.inner_text()
                self.log(f"  - '{label.strip()}'")
                if t["time_management"].lower() in label.strip().lower():
                    link.click()
                    self.page.wait_for_load_state("networkidle")
                    self.page.wait_for_timeout(1000)
                    self.log("✓ En Gestión de tiempo")
                    return
            raise Exception(f"No se encontró el enlace '{t['time_management']}' en el menú")
        time_link.first.click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1000)
        self.log("✓ En Gestión de tiempo")
    def click_this_week(self):
        """
        Hace clic en 'Esta semana' / 'This Week'.
        Es un elemento con role='link' y data-automation-id='label',
        NO un botón. El texto incluye las horas ej: 'Esta semana (0 Horas)'.
        """
        t = self.texts
        self.log(f"Haciendo clic en '{t['this_week']}'...")
        # Buscar por role="link" que contenga el texto clave (sin importar las horas)
        link = self.page.locator(
            '[data-automation-id="label"][role="link"]'
        ).filter(has_text=t["this_week"]).first
        link.click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1000)
        self.log("✓ En calendario de horas")
    def open_enter_time_by_type(self):
        """
        Abre Acciones → Introducción de horas por tipo.
        El botón Acciones tiene data-automation-id consistente.
        """
        t = self.texts
        self.log("Abriendo menú Acciones...")
        # Botón Acciones — buscar por texto del idioma
        actions_btn = self.page.get_by_role("button", name=t["actions"], exact=False)
        actions_btn.click()
        self.page.wait_for_timeout(800)
        # Primera opción del dropdown — siempre es "Introducción de horas por tipo"
        self.log(f"Seleccionando '{t['enter_time_by_type']}'...")
        first_option = self.page.get_by_role("menuitem").first
        first_option.click()
        self.page.wait_for_timeout(1500)
        self.log("✓ Modal de selección de semana abierto")
    def select_week_in_modal(self, week_start_date: str):
        """
        Selecciona la semana correcta en el modal de selección.
        week_start_date: 'YYYY-MM-DD' del domingo de la semana.
        """
        from datetime import datetime
        t = self.texts
        start = datetime.strptime(week_start_date, "%Y-%m-%d")
        # El modal muestra fechas en formato DD/MM/YYYY
        start_formatted = start.strftime("%d/%m/%Y")
        self.log(f"Seleccionando semana del {start_formatted}...")
        # Los radio buttons del modal — buscar por el texto de la fecha
        radios = self.page.get_by_role("radio").all()
        selected = False
        for radio in radios:
            # Leer el texto del elemento padre (label)
            parent_text = radio.evaluate(
                "el => el.closest('label') ? el.closest('label').textContent : "
                "(el.parentElement ? el.parentElement.textContent : '')"
            )
            if start_formatted in (parent_text or ""):
                radio.click()
                selected = True
                self.log(f"✓ Semana seleccionada: {parent_text.strip()}")
                break
        if not selected:
            # Fallback: seleccionar el primer radio disponible
            self.log("⚠ Semana exacta no encontrada, seleccionando la primera disponible")
            self.page.get_by_role("radio").first.click()
        # Clic en Siguiente / Next / Avançar
        self.page.get_by_role("button", name=t["next_button"], exact=False).click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1500)
        self.log("✓ Semana confirmada, tabla lista")


    def add_worktags(self, worktags: list[str]):
        """
        Agrega worktags a la última fila añadida.
        worktags: lista de strings, ej. ["Project-123", "Cost Center A"]
        """
        # Selector estable para la columna Worktags (última fila con multiselect)
        WORKTAGS_CELL = "td.wd-82e73282-c6ab-4dbc-b01b-d29e58810b3f"

        # Obtener todas las celdas de worktags con multiselect (excluye header y footer)
        worktag_cells = self.page.locator(
            f"{WORKTAGS_CELL} [data-automation-id='multiSelectContainer']"
        )

        # Siempre trabajamos en la ÚLTIMA fila añadida
        last_cell = worktag_cells.last()

        for tag in worktags:
            # Click en el input de búsqueda dentro del multiselect
            search_input = last_cell.locator("[data-automation-id='searchBox'] input, "
                                             "[data-automation-id='multiselectInputContainer'] input")
            search_input.click()
            search_input.fill(tag)

            # Esperar que aparezcan las opciones
            self.page.wait_for_selector(
                "[data-automation-id='promptOption']", 
                timeout=5000
            )

            # Seleccionar la primera opción que coincida
            options = self.page.locator("[data-automation-id='promptOption']")
            option_count = options.count()

            if option_count == 0:
                raise Exception(f"No se encontró el worktag: '{tag}'")

            # Buscar coincidencia exacta primero, si no tomar la primera
            selected = False
            for i in range(option_count):
                opt = options.nth(i)
                if tag.lower() in opt.inner_text().lower():
                    opt.click()
                    selected = True
                    break

            if not selected:
                options.first().click()

            self.page.wait_for_timeout(500)

    def add_project_row(self, task_name: str, hours: dict, week_dates: list, worktags: list = None):
        """
        Agrega una fila para un proyecto y llena sus horas.
        ...
        worktags : list, opcional
            Lista de strings con los worktags a asignar, ej. ["Project-123", "CC-001"]
        """
        self.log(f"    Agregando fila para: {task_name}")

        # 1) Agregar nueva fila
        self.page.locator('[data-automation-id="addRow"]').click()
        self.page.wait_for_timeout(800)

        # 2) Localizar el input de "Tipo de jornada" en la nueva fila (primera)
        tipo_input = self.page.locator('tbody input[placeholder="Buscar"]').first
        tipo_input.click()
        self.page.wait_for_timeout(200)

        try:
            tipo_input.clear()
        except Exception:
            tipo_input.fill("")

        tipo_input.type(task_name, delay=60)
        self.page.wait_for_timeout(700)

        tipo_input.press("Enter")
        self.page.wait_for_timeout(2500)

        # 3) Llenar Worktags si se proporcionaron
        if worktags:
            self._fill_worktags(worktags)

        # 4) Buscar la primera fila real con campos de horas
        rows_with_inputs = self.page.locator('tbody tr').filter(
            has=self.page.locator('[data-automation-id="numericInput"]')
        )
        first_data_row = rows_with_inputs.first
        hour_inputs = first_data_row.locator('[data-automation-id="numericInput"]')
        hour_count = hour_inputs.count()
        self.log(f"    → {hour_count} campos de horas encontrados")

        # 5) Llenar horas por día
        for i, date_str in enumerate(week_dates):
            if i >= hour_count:
                self.log(f"    ⚠ No hay más columnas de horas para {date_str}")
                break

            val = hours.get(date_str, 0.0)
            inp = hour_inputs.nth(i)

            try:
                inp.click()
                self.page.wait_for_timeout(80)

                if val > 0:
                    inp.click(click_count=3)
                    self.page.wait_for_timeout(50)
                    try:
                        inp.press("Backspace")
                        self.page.wait_for_timeout(50)
                    except Exception:
                        pass
                    inp.type(format_hours(val), delay=40)
                    inp.press("Tab")
                    self.page.wait_for_timeout(150)
                else:
                    inp.press("Tab")
                    self.page.wait_for_timeout(80)

            except Exception as e:
                self.log(f"    ⚠ Error llenando {date_str} con valor {val}: {e}")
                raise


    def _fill_worktags(self, worktags: list):
        for tag in worktags:
            self.log(f"    → Worktag: {tag}")

            # El segundo input "Buscar" en tbody es siempre Worktags
            worktag_input = self.page.locator('tbody input[placeholder="Buscar"]').nth(1)
            worktag_input.click()
            self.page.wait_for_timeout(200)

            try:
                worktag_input.clear()
            except Exception:
                worktag_input.fill("")

            worktag_input.type(tag, delay=60)
            self.page.wait_for_timeout(700)

            worktag_input.press("Enter")
            self.page.wait_for_timeout(500)



    '''
    def go_to_next_week(self):
        """Clic en ... → Siguiente semana."""
        t = self.texts
        self.log("Avanzando a siguiente semana...")
        # Botón ... — selector correcto por data-automation-id
        self.page.locator('[data-automation-id="uic_moreButton"]').click()
        self.page.wait_for_timeout(800)
        # Clic en "Siguiente semana" por texto del idioma
        self.page.get_by_role("menuitem", name=t["next_week"], exact=False).click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1500)
        self.log("✓ Siguiente semana lista")
    '''

    def save(self):
        """Hace clic en Guardar (no Guardar y cerrar)."""
        t = self.texts
        self.log("Guardando...")
        # Buscar botón exacto por data-automation-id o por texto exacto
        # "Guardar" es diferente de "Guardar y cerrar"
        save_btn = self.page.locator('[data-automation-id="wd-CommandButton_uic_saveButton"]')
        if save_btn.count() == 0:
            # Fallback: buscar botón cuyo texto sea exactamente el de "save"
            all_btns = self.page.get_by_role("button").all()
            for btn in all_btns:
                try:
                    if btn.inner_text().strip() == t["save"]:
                        btn.click()
                        self.page.wait_for_timeout(2000)
                        self.log("✓ Guardado")
                        return
                except Exception:
                    continue
        else:
            save_btn.click()
            self.page.wait_for_timeout(2000)
            self.log("✓ Guardado")

    def save_and_close(self):
        """Hace clic en Guardar y cerrar."""
        t = self.texts
        self.log("Guardando y cerrando...")
        self.page.get_by_role("button", name=t["save_and_close"], exact=False).click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1500)
        self.log("✓ Guardado y cerrado")

    def go_to_next_week(self):
        """
        Avanza a la siguiente semana abriendo el menú de acciones (...)
        y seleccionando la opción correspondiente según el idioma detectado.

        Usa selectores robustos:
        - Botón de tres puntos: intenta por data-automation-id y luego por el SVG
        - Opción del menú: role='option' / data-automation-dropdown-option
        """
        t = self.texts
        self.log("Avanzando a siguiente semana...")

        more_clicked = False

        # ---------------------------------------------------------
        # 1) Intento principal: botón robusto conocido
        # ---------------------------------------------------------
        try:
            more_btn = self.page.locator('[data-automation-id="uic_moreButton"]').last
            if more_btn.count() > 0 and more_btn.is_visible():
                more_btn.click()
                more_clicked = True
                self.log("✓ Menú abierto con data-automation-id='uic_moreButton'")
                self.page.wait_for_timeout(800)
        except Exception as e:
            self.log(f"  ⚠ Falló uic_moreButton: {e}")

        # ---------------------------------------------------------
        # 2) Fallback: abrir menú desde el ícono SVG
        # ---------------------------------------------------------
        if not more_clicked:
            try:
                svg_menu = self.page.locator("svg.wd-icon-related-actions").last
                if svg_menu.count() > 0 and svg_menu.is_visible():
                    clickable_parent = svg_menu.locator(
                        "xpath=ancestor::*[self::button or @role='button' or @tabindex][1]"
                    )
                    if clickable_parent.count() > 0:
                        clickable_parent.click()
                        more_clicked = True
                        self.log("✓ Menú abierto desde ancestro clickeable del SVG")
                        self.page.wait_for_timeout(800)
                    else:
                        svg_menu.click(force=True)
                        more_clicked = True
                        self.log("✓ Menú abierto con clic forzado sobre SVG")
                        self.page.wait_for_timeout(800)
            except Exception as e:
                self.log(f"  ⚠ Falló intento con SVG related actions: {e}")

        if not more_clicked:
            raise Exception("No se pudo abrir el menú de tres puntos para avanzar de semana.")

        # ---------------------------------------------------------
        # 3) Seleccionar la opción 'Siguiente semana'
        #    IMPORTANTE: el elemento tiene role='option', no 'menuitem'
        # ---------------------------------------------------------
        selected = False

        # Opción A: por atributos de automatización + texto del idioma detectado
        try:
            next_option = self.page.locator(
                '[data-automation-dropdown-option="dropdown-option"]'
            ).filter(has_text=t["next_week"]).first

            if next_option.count() > 0 and next_option.is_visible():
                next_option.click()
                selected = True
                self.log(f"✓ Opción '{t['next_week']}' seleccionada")
        except Exception as e:
            self.log(f"  ⚠ Falló selección por data-automation-dropdown-option: {e}")

        # Opción B: por role='option'
        if not selected:
            try:
                next_option = self.page.get_by_role("option", name=t["next_week"], exact=False).first
                if next_option.count() > 0 and next_option.is_visible():
                    next_option.click()
                    selected = True
                    self.log(f"✓ Opción '{t['next_week']}' seleccionada por role='option'")
            except Exception as e:
                self.log(f"  ⚠ Falló selección por role='option': {e}")

        # Opción C: recorrer todas las opciones visibles y comparar texto
        if not selected:
            try:
                options = self.page.locator('[data-automation-dropdown-option="dropdown-option"]')
                count = options.count()
                self.log(f"  Opciones visibles en dropdown: {count}")

                for i in range(count):
                    opt = options.nth(i)
                    try:
                        txt = " ".join(opt.inner_text().split()).strip()
                        self.log(f"    [{i}] {txt}")
                        if t["next_week"].lower() in txt.lower():
                            opt.click()
                            selected = True
                            self.log(f"✓ Opción '{txt}' seleccionada por recorrido manual")
                            break
                    except Exception:
                        continue
            except Exception as e:
                self.log(f"  ⚠ Falló recorrido manual de opciones: {e}")

        if not selected:
            raise Exception(
                f"Se abrió el menú, pero no se encontró la opción de siguiente semana "
                f"para el idioma '{self.lang}' ({t['next_week']})."
            )

        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1500)
        self.log("✓ Siguiente semana lista")

    def run(self, weeks_data: dict):
        """
        Ejecuta el proceso completo de llenado de todas las semanas.
        weeks_data: resultado de csv_reader.parse_csv()
        """
        total_weeks = len(weeks_data)
        week_num = 0
        for week_start, projects in weeks_data.items():
            week_num += 1
            self.log(f"\\n{'='*45}")
            self.log(f"📅 Semana {week_num}/{total_weeks}  |  inicio: {week_start}")
            self.log(f"{'='*45}")
            week_dates = get_week_dates(week_start)
            is_last_week = (week_num == total_weeks)
            total_projects = len(projects)
            for proj_num, project in enumerate(projects, 1):
                task = project["task_name"]
                hours = project["hours"]
                #worktags = project["grant_id"]
                self.log(f"  [{proj_num}/{total_projects}] {task}")
                for attempt in range(MAX_RETRIES):
                    try:
                        self.add_project_row(task, hours, week_dates)
                        #if worktags == '0':
                        #    self.add_project_row(task, hours, week_dates)
                        #else:
                        #    self.add_project_row(task, hours, week_dates, worktags)
                        self.log(f"  ✓ {task}")
                        break
                    except Exception as e:
                        if attempt < MAX_RETRIES - 1:
                            self.log(f"  ⚠ Reintento {attempt+2}/{MAX_RETRIES}...")
                            self.page.wait_for_timeout(2000)
                        else:
                            self.log(f"  ✗ Error en '{task}': {e}")
            # Pedir confirmación antes de guardar
            confirmed = self.confirm(
                f"Semana {week_num}/{total_weeks}  —  inicio: {week_start}\n\n"
                "Verifica que todos los proyectos y horas se vean correctos en Workday.\n\n"
                "¿Confirmas guardar esta semana y continuar?"
            )
            if not confirmed:
                raise Exception("Proceso cancelado por el usuario antes de guardar.")
            # Guardar
            self.save()
            # Ir a siguiente semana o cerrar
            if not is_last_week:
                self.go_to_next_week()
            else:
                self.save_and_close()
                self.log("\\n✅ ¡Proceso completado exitosamente!")
    def close(self):
        """Cierra la conexión con el navegador."""
        if self.playwright:
            self.playwright.stop()