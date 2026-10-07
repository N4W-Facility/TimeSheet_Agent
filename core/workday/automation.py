# ============================================================
# AUTOMATIZACIÓN DE WORKDAY CON PLAYWRIGHT
# Selectores basados en data-automation-id (independiente del idioma)
# ============================================================
import time
from datetime import date
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from config import TIMEOUT, MAX_RETRIES, CDP_URL, WORKDAY_TIME_CALENDAR_URL
from core.workday.i18n import detect_language, get_texts
from core.workday.csv_reader import get_week_dates, format_hours
from core.workday.matching import best_option, option_task, week_label_matches, week_months
class WorkdayAutomation:
    def __init__(self, log_callback=None, confirm_callback=None):
        self.playwright = None
        self.browser = None
        self.page = None
        self.texts = None
        self.lang = None
        self.log = log_callback if log_callback else print
        self.confirm = confirm_callback if confirm_callback else lambda msg: True
        self.notes = []     # selecciones con varias opciones en la semana actual
    def connect(self):
        """Se conecta al navegador ya abierto vía CDP."""
        self.log("Connecting to browser...")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.connect_over_cdp(CDP_URL)
        context = self.browser.contexts[0]
        self.page = context.pages[0]
        self.page.set_default_timeout(TIMEOUT)
        self.log("✓ Connected to browser")
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
        self.log(f"✓ Workday language: {self.lang.upper()}")
    def navigate_to_time_management(self):
        """
        Navega a Gestión de tiempo desde el menú principal.
        Usa aria-label que es independiente del renderizado visual.
        """
        t = self.texts
        # Abrir menú
        self.log("Opening main menu...")
        self.page.locator('[data-automation-id="globalNavButton"]').click()
        self.page.wait_for_timeout(1200)
        # Buscar el link por aria-label exacto en el idioma detectado
        self.log(f"Looking for '{t['time_management']}'...")
        time_link = self.page.locator(
            f'[data-automation-id="globalNavAppItemLink"][aria-label="{t["time_management"]}"]'
        )
        count = time_link.count()
        self.log(f"  Links found with that aria-label: {count}")
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
                    self.log("✓ In Time Management")
                    return
            raise Exception(f"Link '{t['time_management']}' not found in menu")
        time_link.first.click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1000)
        self.log("✓ In Time Management")
    def click_this_week(self):
        """
        Hace clic en 'Esta semana' / 'This Week'.
        Es un elemento con role='link' y data-automation-id='label',
        NO un botón. El texto incluye las horas ej: 'Esta semana (0 Horas)'.
        """
        t = self.texts
        self.log(f"Clicking '{t['this_week']}'...")
        # Buscar por role="link" que contenga el texto clave (sin importar las horas)
        link = self.page.locator(
            '[data-automation-id="label"][role="link"]'
        ).filter(has_text=t["this_week"]).first
        link.click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1000)
        self.log("✓ In time calendar")
    def open_enter_time_by_type(self):
        """
        Abre Acciones → Introducción de horas por tipo.
        El botón Acciones tiene data-automation-id consistente.
        """
        t = self.texts
        self.log("Opening Actions menu...")
        # Botón Acciones — buscar por texto del idioma
        actions_btn = self.page.get_by_role("button", name=t["actions"], exact=False)
        actions_btn.click()
        self.page.wait_for_timeout(800)
        # Primera opción del dropdown — siempre es "Introducción de horas por tipo"
        self.log(f"Selecting '{t['enter_time_by_type']}'...")
        first_option = self.page.get_by_role("menuitem").first
        first_option.click()
        self.page.wait_for_timeout(1500)
        self.log("✓ Week selection dialog open")
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
        self.log(f"Selecting week of {start_formatted}...")
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
                self.log(f"✓ Week selected: {parent_text.strip()}")
                break
        if not selected:
            # Fallback: seleccionar el primer radio disponible
            self.log("⚠ Exact week not found, selecting the first available")
            self.page.get_by_role("radio").first.click()
        # Clic en Siguiente / Next / Avançar
        self.page.get_by_role("button", name=t["next_button"], exact=False).click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1500)
        self.log("✓ Week confirmed, table ready")

    def open_week_table(self, week_start: str):
        """
        Llega a la tabla de la semana sin depender del idioma:
        calendario (URL fija) → ◀/▶ hasta el mes → Acciones → 1ª opción (por tipo)
        → semana → Siguiente. Una semana que cruza meses se busca en ambos.
        week_start: 'YYYY-MM-DD' del domingo de la semana.
        """
        dialog = self.page.locator('[data-automation-id="popUpDialog"]')
        for year, month in week_months(week_start):
            self._open_week_dialog(year, month)
            for radio in dialog.get_by_role("radio").all():
                label = radio.get_attribute("aria-label") or radio.evaluate(
                    "el => el.labels && el.labels[0] ? el.labels[0].textContent : ''")
                if week_label_matches(label, week_start):
                    radio.check(force=True)     # el input es invisible (opacity 0), Workday pinta encima
                    self.log(f"✓ Week selected: {label.strip()}")
                    break
            else:
                dialog.locator('[data-automation-id="wd-CommandButton_uic_cancelButton"]').click()
                dialog.wait_for(state="hidden")
                continue
            break
        else:
            raise Exception(f"Week starting {week_start} is not offered by Workday.")
        # Siguiente: el botón de comando del diálogo que no es Cancelar
        dialog.locator('button[data-automation-id="wd-CommandButton"]').last.click()
        self.page.locator('[data-automation-id="addRow"]').wait_for(state="visible")
        self.page.wait_for_timeout(1000)
        self.log("✓ Week table ready")

    def _open_week_dialog(self, year: int, month: int):
        """Calendario en year/month (◀/▶ desde el mes actual) → Acciones → por tipo."""
        self.log(f"Opening the Workday time calendar ({year}-{month:02d})...")
        self.page.goto(WORKDAY_TIME_CALENDAR_URL)
        actions_btn = self.page.locator('[data-testid="actions_button"]')
        actions_btn.wait_for(state="visible")
        today = date.today()
        steps = (year - today.year) * 12 + (month - today.month)
        arrow = self.page.locator('[data-testid="arrows_button_%s"]' % ("next" if steps > 0 else "previous"))
        date_range = self.page.locator('[data-testid="date_range"]')
        for _ in range(abs(steps)):
            shown = date_range.inner_text()
            arrow.click()
            self.page.wait_for_function(
                "t => { const e = document.querySelector('[data-testid=\"date_range\"]');"
                " return e && e.innerText !== t; }", arg=shown)
        actions_btn.click()
        # Las opciones traen el texto traducido; la posición es estable (0 = por tipo)
        self.page.locator('[role="menuitem"][data-id="0"]').click()
        try:
            self.page.locator('[data-automation-id="popUpDialog"] [data-automation-id="radioBtn"]'
                              ).first.wait_for(state="visible")
        except PlaywrightTimeout:
            raise Exception("The Actions menu did not open the week selection — "
                            "Workday may have changed the order of its options.")

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
                raise Exception(f"Worktag not found: '{tag}'")

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
        self.log(f"    Adding row for: {task_name}")

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

        row = tipo_input.evaluate_handle("e => e.closest('tr')")
        tipo_input.type(task_name, delay=60)
        self.page.wait_for_timeout(700)

        tipo_input.press("Enter")
        self.page.wait_for_timeout(2500)
        self._pick_task(task_name, row)

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
        self.log(f"    → {hour_count} hour fields found")

        # 5) Llenar horas por día
        for i, date_str in enumerate(week_dates):
            if i >= hour_count:
                self.log(f"    ⚠ No more hour columns for {date_str}")
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
                self.log(f"    ⚠ Error filling {date_str} with {val}: {e}")
                raise


    def _pick_task(self, task_name: str, row):
        """
        Tras Enter, Workday elige solo si hay un resultado. Con varios abre la lista:
        se elige el de mayor coincidencia y se anota para la confirmación de la semana.
        """
        options = self.page.locator('[data-automation-id="promptLeafNode"]')
        labels = [" ".join(t.split()) for t in options.all_inner_texts()]
        if len(labels) > 1:
            best, score = best_option(task_name, labels)
            options.nth(best).click()
            self.page.wait_for_timeout(1500)
            self.notes.append(f"• {task_name}: {len(labels)} options → chose\n"
                              f"  '{labels[best]}' ({score:.0%} match)")
            self.log(f"    ⚠ {len(labels)} options for '{task_name}' → "
                     f"'{option_task(labels[best])}' ({score:.0%} match)")
        if not row.evaluate("r => !!r && !!r.querySelector('[data-automation-id=\"selectedItem\"]')"):
            raise Exception(f"Workday did not select a work type for '{task_name}'")

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
        self.log("Moving to next week...")
        # Botón ... — selector correcto por data-automation-id
        self.page.locator('[data-automation-id="uic_moreButton"]').click()
        self.page.wait_for_timeout(800)
        # Clic en "Siguiente semana" por texto del idioma
        self.page.get_by_role("menuitem", name=t["next_week"], exact=False).click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1500)
        self.log("✓ Next week ready")
    '''

    def save(self):
        """Hace clic en Guardar (no Guardar y cerrar)."""
        t = self.texts
        self.log("Saving...")
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
                        self.log("✓ Saved")
                        return
                except Exception:
                    continue
        else:
            save_btn.click()
            self.page.wait_for_timeout(2000)
            self.log("✓ Saved")

    def save_and_close(self):
        """Hace clic en Guardar y cerrar."""
        t = self.texts
        self.log("Saving and closing...")
        self.page.get_by_role("button", name=t["save_and_close"], exact=False).click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1500)
        self.log("✓ Saved and closed")

    def go_to_next_week(self):
        """
        Avanza a la siguiente semana abriendo el menú de acciones (...)
        y seleccionando la opción correspondiente según el idioma detectado.

        Usa selectores robustos:
        - Botón de tres puntos: intenta por data-automation-id y luego por el SVG
        - Opción del menú: role='option' / data-automation-dropdown-option
        """
        t = self.texts
        self.log("Moving to next week...")

        more_clicked = False

        # ---------------------------------------------------------
        # 1) Intento principal: botón robusto conocido
        # ---------------------------------------------------------
        try:
            more_btn = self.page.locator('[data-automation-id="uic_moreButton"]').last
            if more_btn.count() > 0 and more_btn.is_visible():
                more_btn.click()
                more_clicked = True
                self.log("✓ Menu opened via data-automation-id='uic_moreButton'")
                self.page.wait_for_timeout(800)
        except Exception as e:
            self.log(f"  ⚠ uic_moreButton failed: {e}")

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
                        self.log("✓ Menu opened via clickable SVG ancestor")
                        self.page.wait_for_timeout(800)
                    else:
                        svg_menu.click(force=True)
                        more_clicked = True
                        self.log("✓ Menu opened via forced SVG click")
                        self.page.wait_for_timeout(800)
            except Exception as e:
                self.log(f"  ⚠ SVG related-actions attempt failed: {e}")

        if not more_clicked:
            raise Exception("Could not open the three-dot menu to move to next week.")

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
                self.log(f"✓ Option '{t['next_week']}' selected")
        except Exception as e:
            self.log(f"  ⚠ Selection via data-automation-dropdown-option failed: {e}")

        # Opción B: por role='option'
        if not selected:
            try:
                next_option = self.page.get_by_role("option", name=t["next_week"], exact=False).first
                if next_option.count() > 0 and next_option.is_visible():
                    next_option.click()
                    selected = True
                    self.log(f"✓ Option '{t['next_week']}' selected via role='option'")
            except Exception as e:
                self.log(f"  ⚠ Selection via role='option' failed: {e}")

        # Opción C: recorrer todas las opciones visibles y comparar texto
        if not selected:
            try:
                options = self.page.locator('[data-automation-dropdown-option="dropdown-option"]')
                count = options.count()
                self.log(f"  Visible dropdown options: {count}")

                for i in range(count):
                    opt = options.nth(i)
                    try:
                        txt = " ".join(opt.inner_text().split()).strip()
                        self.log(f"    [{i}] {txt}")
                        if t["next_week"].lower() in txt.lower():
                            opt.click()
                            selected = True
                            self.log(f"✓ Option '{txt}' selected by manual scan")
                            break
                    except Exception:
                        continue
            except Exception as e:
                self.log(f"  ⚠ Manual option scan failed: {e}")

        if not selected:
            raise Exception(
                f"Menu opened, but the next-week option was not found "
                f"for language '{self.lang}' ({t['next_week']})."
            )

        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1500)
        self.log("✓ Next week ready")

    def run(self, weeks_data: dict):
        """
        Ejecuta el proceso completo de llenado de todas las semanas.
        weeks_data: resultado de csv_reader.parse_csv()
        """
        total_weeks = len(weeks_data)
        week_num = 0
        # Siempre llegar a la tabla de la primera semana (una tabla ya abierta podría ser de otra semana)
        if weeks_data:
            self.open_week_table(next(iter(weeks_data)))
        for week_start, projects in weeks_data.items():
            week_num += 1
            self.log(f"{'='*45}")
            self.log(f"📅 Week {week_num}/{total_weeks}  |  start: {week_start}")
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
                            self.log(f"  ⚠ Retry {attempt+2}/{MAX_RETRIES}...")
                            self.page.wait_for_timeout(2000)
                        else:
                            self.log(f"  ✗ Error on '{task}': {e}")
            # Pedir confirmación antes de guardar
            notes = ("⚠ Several Workday options, chose the best match — please check:\n"
                     + "\n".join(self.notes) + "\n\n") if self.notes else ""
            self.notes = []
            confirmed = self.confirm(
                f"Week {week_num}/{total_weeks}  —  start: {week_start}\n\n"
                + notes +
                "Check in Workday that all projects and hours look correct.\n\n"
                "Save this week and continue?"
            )
            if not confirmed:
                raise Exception("Cancelled by the user before saving.")
            # Guardar
            self.save()
            # Ir a siguiente semana o cerrar
            if not is_last_week:
                self.go_to_next_week()
            else:
                self.save_and_close()
                self.log("✅ Process completed successfully!")
    def close(self):
        """Cierra la conexión con el navegador."""
        if self.playwright:
            self.playwright.stop()