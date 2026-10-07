# ============================================================
# MENSAJES FIJOS DEL AGENTE (traducción estática, sin LLM)
# Evita una llamada extra al modelo por mensaje → rápido en CPU.
# Idiomas sin traducción → inglés. Tablas y tarjetas: siempre en inglés.
# ============================================================

MESSAGES = {
    "need_email": {
        "en": "Please set your email in Settings (⚙) first.",
        "es": "Primero escribe tu correo en Ajustes (⚙).",
        "pt": "Primeiro informe seu e-mail em Configurações (⚙).",
    },
    "llm_down": {
        "en": "⚠ Could not reach the language model: {err}",
        "es": "⚠ No pude conectar con el modelo de lenguaje: {err}",
        "pt": "⚠ Não consegui conectar ao modelo de linguagem: {err}",
    },
    "cancelled": {
        "en": "Cancelled. Nothing else was changed.",
        "es": "Cancelado. No se cambió nada más.",
        "pt": "Cancelado. Nada mais foi alterado.",
    },
    "error": {
        "en": "⚠ Error: {err}",
        "es": "⚠ Error: {err}",
        "pt": "⚠ Erro: {err}",
    },
    "need_period": {
        "en": "Which period? Tell me a month (e.g. October 2026) or the dates.",
        "es": "¿Qué periodo? Dime un mes (p. ej. octubre 2026) o las fechas.",
        "pt": "Qual período? Diga um mês (ex.: outubro 2026) ou as datas.",
    },
    "need_month": {
        "en": "Which month? (e.g. October 2026)",
        "es": "¿Qué mes? (p. ej. octubre 2026)",
        "pt": "Qual mês? (ex.: outubro 2026)",
    },
    "need_project": {
        "en": "Which project code? (e.g. OF0104)",
        "es": "¿Qué código de proyecto? (p. ej. OF0104)",
        "pt": "Qual código de projeto? (ex.: OF0104)",
    },
    "need_target": {
        "en": "What should the dedication to {code} be? e.g. 30% or 40 h per month.",
        "es": "¿Cuál debería ser tu dedicación a {code}? p. ej. 30% o 40 h al mes.",
        "pt": "Qual deveria ser sua dedicação a {code}? ex.: 30% ou 40 h por mês.",
    },
    "read_first": {
        "en": "First read your hours from Outlook. Write: “{phrase}”.",
        "es": "Primero lee tus horas de Outlook. Escribe: “{phrase}”.",
        "pt": "Primeiro leia suas horas do Outlook. Escreva: “{phrase}”.",
    },
    "read_done": {
        "en": "✓ Hours read for {period}: {total} h in {n} projects. Review the balance above.",
        "es": "✓ Horas leídas de {period}: {total} h en {n} proyectos. Revisa el balance de arriba.",
        "pt": "✓ Horas lidas de {period}: {total} h em {n} projetos. Revise o balanço acima.",
    },
    "next_prorate": {
        "en": "Next step: {codes} must be prorated before Workday. Write: “{phrase}”.",
        "es": "Siguiente paso: {codes} se debe prorratear antes de Workday. Escribe: “{phrase}”.",
        "pt": "Próximo passo: {codes} deve ser rateado antes do Workday. Escreva: “{phrase}”.",
    },
    "next_workday": {
        "en": "Next step: if the balance looks right, write: “{phrase}”.",
        "es": "Siguiente paso: si el balance está bien, escribe: “{phrase}”.",
        "pt": "Próximo passo: se o balanço estiver certo, escreva: “{phrase}”.",
    },
    "no_prorate_needed": {
        "en": "No project in {period} needs prorating.",
        "es": "Ningún proyecto de {period} necesita prorrateo.",
        "pt": "Nenhum projeto de {period} precisa de rateio.",
    },
    "prorate_done": {
        "en": "✓ Prorated hours saved. Next step: “{phrase}”.",
        "es": "✓ Horas prorrateadas guardadas. Siguiente paso: “{phrase}”.",
        "pt": "✓ Horas rateadas salvas. Próximo passo: “{phrase}”.",
    },
    "workday_month_only": {
        "en": "Workday uses the full calendar month. Read a month first: “{phrase}”.",
        "es": "Workday usa el mes calendario completo. Primero lee un mes: “{phrase}”.",
        "pt": "O Workday usa o mês completo. Primeiro leia um mês: “{phrase}”.",
    },
    "must_prorate": {
        "en": "{codes} must be prorated before filling Workday. Write: “{phrase}”.",
        "es": "{codes} se debe prorratear antes de llenar Workday. Escribe: “{phrase}”.",
        "pt": "{codes} deve ser rateado antes de preencher o Workday. Escreva: “{phrase}”.",
    },
    "workday_done": {
        "en": "✓ Workday filled for {period}. Next you can write: “{a}” or “{b}”.",
        "es": "✓ Workday llenado para {period}. Ahora puedes escribir: “{a}” o “{b}”.",
        "pt": "✓ Workday preenchido para {period}. Agora você pode escrever: “{a}” ou “{b}”.",
    },
    "workday_week_done": {
        "en": "✓ Workday filled for the week {period}.",
        "es": "✓ Workday llenado para la semana {period}.",
        "pt": "✓ Workday preenchido para a semana {period}.",
    },
    "workday_week_empty": {
        "en": "There are no hours to fill in the week {period}.",
        "es": "No hay horas para llenar en la semana {period}.",
        "pt": "Não há horas para preencher na semana {period}.",
    },
    "workday_save_title": {
        "en": "Save this week in Workday?",
        "es": "¿Guardar esta semana en Workday?",
        "pt": "Salvar esta semana no Workday?",
    },
    "workday_save_warning": {
        "en": "⚠ Saving records these hours in Workday. Check the Chrome table before saving.",
        "es": "⚠ Guardar registra estas horas en Workday. Revisa la tabla en Chrome antes de guardar.",
        "pt": "⚠ Salvar registra estas horas no Workday. Confira a tabela no Chrome antes de salvar.",
    },
    "workday_save_ok": {"en": "Save in Workday", "es": "Guardar en Workday", "pt": "Salvar no Workday"},
    "workday_save_cancel": {"en": "Don't save", "es": "No guardar", "pt": "Não salvar"},
    "workday_not_saved": {
        "en": "That week was not saved in Workday (weeks saved before it stay saved). "
              "In Chrome you can review or discard the unsaved changes.",
        "es": "Esa semana no se guardó en Workday (las semanas guardadas antes siguen guardadas). "
              "En Chrome puedes revisar o descartar los cambios sin guardar.",
        "pt": "Essa semana não foi salva no Workday (as semanas salvas antes continuam salvas). "
              "No Chrome você pode revisar ou descartar as alterações não salvas.",
    },
    "n4w_send_title": {
        "en": "Submit these hours to N4W Facility? ({period})",
        "es": "¿Enviar estas horas a N4W Facility? ({period})",
        "pt": "Enviar estas horas ao N4W Facility? ({period})",
    },
    "n4w_send_warning": {
        "en": "⚠ This sends your hours to the N4W database (OneDrive). It cannot be undone from here.",
        "es": "⚠ Esto envía tus horas a la base de datos de N4W (OneDrive). No se puede deshacer desde aquí.",
        "pt": "⚠ Isto envia suas horas para a base de dados do N4W (OneDrive). Não pode ser desfeito daqui.",
    },
    "n4w_send_ok": {"en": "Submit to N4W", "es": "Enviar a N4W", "pt": "Enviar ao N4W"},
    "n4w_send_cancel": {"en": "Don't submit", "es": "No enviar", "pt": "Não enviar"},
    "n4w_not_sent": {
        "en": "Nothing was submitted to N4W. The file stays only on your computer: {path}",
        "es": "No se envió nada a N4W. El archivo quedó solo en tu equipo: {path}",
        "pt": "Nada foi enviado ao N4W. O arquivo ficou só no seu computador: {path}",
    },
    "n4w_done": {
        "en": "✓ N4W Facility submitted ({period}).",
        "es": "✓ N4W Facility enviado ({period}).",
        "pt": "✓ N4W Facility enviado ({period}).",
    },
    "hello": {
        "en": "Hi! Here is where you are:",
        "es": "¡Hola! Así vas:",
        "pt": "Olá! Veja onde você está:",
    },
    "status_next": {
        "en": "{period}: {n} step(s) pending (see the card). Next: “{phrase}”.",
        "es": "{period}: {n} paso(s) pendiente(s) (ver la tarjeta). Siguiente: “{phrase}”.",
        "pt": "{period}: {n} passo(s) pendente(s) (veja o cartão). Próximo: “{phrase}”.",
    },
    "status_done": {
        "en": "✓ {period}: everything is done (Workday and N4W). You can ask “{phrase}”.",
        "es": "✓ {period}: todo está hecho (Workday y N4W). Puedes preguntar “{phrase}”.",
        "pt": "✓ {period}: tudo pronto (Workday e N4W). Você pode perguntar “{phrase}”.",
    },
    "close_ready": {
        "en": "✓ {period} looks ready to close: full days, meetings categorized, no blocked projects.",
        "es": "✓ {period} se ve listo para cerrar: días completos, reuniones categorizadas, sin proyectos bloqueados.",
        "pt": "✓ {period} parece pronto para fechar: dias completos, reuniões categorizadas, sem projetos bloqueados.",
    },
    "close_issues": {
        "en": "{period}: {n} thing(s) to review before closing (see the card).",
        "es": "{period}: {n} cosa(s) por revisar antes de cerrar (ver la tarjeta).",
        "pt": "{period}: {n} item(ns) para revisar antes de fechar (veja o cartão).",
    },
    "quick_project": {
        "en": "{code}: {hours} h in {period} ({pct}% of your {total} h){src}.",
        "es": "{code}: {hours} h en {period} ({pct}% de tus {total} h){src}.",
        "pt": "{code}: {hours} h em {period} ({pct}% das suas {total} h){src}.",
    },
    "quick_project_none": {
        "en": "{code} has no hours in {period}{src}.",
        "es": "{code} no tiene horas en {period}{src}.",
        "pt": "{code} não tem horas em {period}{src}.",
    },
    "quick_total": {
        "en": "{period}: {total} h of {expected} h expected ({days} working days){src}. Most: {top}.",
        "es": "{period}: {total} h de {expected} h esperadas ({days} días laborables){src}. Lo principal: {top}.",
        "pt": "{period}: {total} h de {expected} h esperadas ({days} dias úteis){src}. Principais: {top}.",
    },
    "from_outlook": {
        "en": " — read from Outlook just now", "es": " — leído de Outlook ahora", "pt": " — lido do Outlook agora",
    },
    "need_edit": {
        "en": "Tell me the project, the day and the new hours, e.g. “{phrase}”.",
        "es": "Dime el proyecto, el día y las horas nuevas, p. ej. “{phrase}”.",
        "pt": "Diga o projeto, o dia e as novas horas, ex.: “{phrase}”.",
    },
    "edit_out_of_period": {
        "en": "{day} is not in the period read ({period}).",
        "es": "{day} no está en el periodo leído ({period}).",
        "pt": "{day} não está no período lido ({period}).",
    },
    "edit_virtual": {
        "en": "{code} was already prorated (its hours went to other projects). Edit another project or read the month again.",
        "es": "{code} ya se prorrateó (sus horas pasaron a otros proyectos). Edita otro proyecto o vuelve a leer el mes.",
        "pt": "{code} já foi rateado (suas horas foram para outros projetos). Edite outro projeto ou leia o mês de novo.",
    },
    "edit_done": {
        "en": "✓ {code} on {day}: {old} h → {new} h (day total {total} h). Only the file for Workday changed: Outlook stays as is, so reading again discards this edit and N4W uses Outlook.",
        "es": "✓ {code} el {day}: {old} h → {new} h (total del día {total} h). Solo cambió el archivo para Workday: Outlook queda igual, así que volver a leer descarta este cambio y N4W usa Outlook.",
        "pt": "✓ {code} em {day}: {old} h → {new} h (total do dia {total} h). Só mudou o arquivo do Workday: o Outlook fica igual, então ler de novo descarta esta edição e o N4W usa o Outlook.",
    },
    "edit_workday_again": {
        "en": "Workday was already filled for this month: fill that week again to update it.",
        "es": "Workday ya se llenó para este mes: vuelve a llenar esa semana para actualizarla.",
        "pt": "O Workday já foi preenchido para este mês: preencha essa semana de novo para atualizá-la.",
    },
    "no_prorate_yet": {
        "en": "{period} has not been prorated yet. Write “{phrase}”.",
        "es": "{period} aún no se prorrateó. Escribe “{phrase}”.",
        "pt": "{period} ainda não foi rateado. Escreva “{phrase}”.",
    },
    "categories_synced": {
        "en": "✓ Outlook categories of your projects checked. {cats}",
        "es": "✓ Categorías de Outlook de tus proyectos revisadas. {cats}",
        "pt": "✓ Categorias do Outlook dos seus projetos verificadas. {cats}",
    },
    "absence_cats_created": {
        "en": "I added the leave categories to Outlook (holiday, vacation, sick…): {names}. "
              "Mark each day off as an 8 h block with one of them.",
        "es": "Agregué a Outlook las categorías de licencias (festivo, vacaciones, enfermedad…): {names}. "
              "Marca cada día libre como un bloque de 8 h con una de ellas.",
        "pt": "Adicionei ao Outlook as categorias de licenças (feriado, férias, doença…): {names}. "
              "Marque cada dia de folga como um bloco de 8 h com uma delas.",
    },
    "cats_created": {
        "en": "Created: {names}.", "es": "Creadas: {names}.", "pt": "Criadas: {names}.",
    },
    "cats_existing": {
        "en": "Already in Outlook (kept as they are): {names}.",
        "es": "Ya existían en Outlook (se dejan como están): {names}.",
        "pt": "Já existiam no Outlook (ficam como estão): {names}.",
    },
    "all_categorized": {
        "en": "✓ All your meetings of {period} already have a category.",
        "es": "✓ Todas tus reuniones de {period} ya tienen categoría.",
        "pt": "✓ Todas as suas reuniões de {period} já têm categoria.",
    },
    "meetings_categorized": {
        "en": "✓ {n} meetings categorized in Outlook ({left} still without category). To update the hours write: “{phrase}”.",
        "es": "✓ {n} reuniones categorizadas en Outlook ({left} siguen sin categoría). Para actualizar las horas escribe: “{phrase}”.",
        "pt": "✓ {n} reuniões categorizadas no Outlook ({left} ainda sem categoria). Para atualizar as horas escreva: “{phrase}”.",
    },
    "cats_failed": {
        "en": "⚠ I couldn't reach Outlook to create the categories; write “sync my Outlook categories” later.",
        "es": "⚠ No pude acceder a Outlook para crear las categorías; escribe “sincroniza mis categorías de Outlook” más tarde.",
        "pt": "⚠ Não consegui acessar o Outlook para criar as categorias; escreva “sincronize minhas categorias do Outlook” depois.",
    },
    "no_history": {
        "en": "I have no saved hours for {period}. Write “{a}” or “{b}”.",
        "es": "No tengo horas guardadas de {period}. Escribe “{a}” o “{b}”.",
        "pt": "Não tenho horas salvas de {period}. Escreva “{a}” ou “{b}”.",
    },
    "history_empty": {
        "en": "Your history is empty. Write “{a}” or “{b}”.",
        "es": "Tu historial está vacío. Escribe “{a}” o “{b}”.",
        "pt": "Seu histórico está vazio. Escreva “{a}” ou “{b}”.",
    },
    "unknown_project": {
        "en": "{code} has no hours in your history.",
        "es": "{code} no tiene horas en tu historial.",
        "pt": "{code} não tem horas no seu histórico.",
    },
    "target_saved": {
        "en": "✓ Target for {code}: {target}. Your monthly average so far: {avg}.",
        "es": "✓ Objetivo para {code}: {target}. Tu promedio mensual hasta ahora: {avg}.",
        "pt": "✓ Meta para {code}: {target}. Sua média mensal até agora: {avg}.",
    },
    "missing_targets": {
        "en": "No target dedication yet for: {codes}. You can write, e.g. “{phrase}”.",
        "es": "Aún sin dedicación objetivo: {codes}. Puedes escribir, p. ej. “{phrase}”.",
        "pt": "Ainda sem dedicação alvo: {codes}. Você pode escrever, ex.: “{phrase}”.",
    },
    "no_alerts": {
        "en": "✓ No alerts for {period}.",
        "es": "✓ Sin alertas para {period}.",
        "pt": "✓ Sem alertas para {period}.",
    },
    "history_loaded": {
        "en": "✓ History: {done} months read, {skipped} already saved, {failed} without data.",
        "es": "✓ Historial: {done} meses leídos, {skipped} ya guardados, {failed} sin datos.",
        "pt": "✓ Histórico: {done} meses lidos, {skipped} já salvos, {failed} sem dados.",
    },
    "resume_prorate": {
        "en": "Last time you read {period} ({at}); {codes} still must be prorated. To continue write “{phrase}”, or read another period.",
        "es": "La última vez leíste {period} ({at}); falta prorratear {codes}. Para seguir escribe “{phrase}”, o lee otro periodo.",
        "pt": "Da última vez você leu {period} ({at}); falta ratear {codes}. Para continuar escreva “{phrase}”, ou leia outro período.",
    },
    "resume_workday": {
        "en": "{period} is ready ({state}) but Workday was not filled yet. To continue write “{phrase}”, or read another period.",
        "es": "{period} está listo ({state}) pero aún no se llenó Workday. Para seguir escribe “{phrase}”, o lee otro periodo.",
        "pt": "{period} está pronto ({state}) mas o Workday ainda não foi preenchido. Para continuar escreva “{phrase}”, ou leia outro período.",
    },
    "resume_done": {
        "en": "Last completed: Workday filled for {period}. You can write “{a}” or “{b}”.",
        "es": "Lo último completado: Workday llenado para {period}. Puedes escribir “{a}” o “{b}”.",
        "pt": "Último concluído: Workday preenchido para {period}. Você pode escrever “{a}” ou “{b}”.",
    },
    "global_ok": {
        "en": "✓ Global project list (N4W_Task_Details) downloaded ({at}): {n} active projects.",
        "es": "✓ Base global de proyectos (N4W_Task_Details) descargada ({at}): {n} proyectos activos.",
        "pt": "✓ Base global de projetos (N4W_Task_Details) baixada ({at}): {n} projetos ativos.",
    },
    "global_stale": {
        "en": "⚠ Could not download N4W_Task_Details; using the local copy from {at} ({n} active projects).",
        "es": "⚠ No pude descargar N4W_Task_Details; uso la copia local del {at} ({n} proyectos activos).",
        "pt": "⚠ Não consegui baixar o N4W_Task_Details; uso a cópia local de {at} ({n} projetos ativos).",
    },
    "global_failed": {
        "en": "⚠ Could not get N4W_Task_Details ({err}). I can't check projects against the global list.",
        "es": "⚠ No pude obtener N4W_Task_Details ({err}). No puedo comparar con la base global.",
        "pt": "⚠ Não consegui obter o N4W_Task_Details ({err}). Não posso comparar com a base global.",
    },
    "blocked_projects": {
        "en": "⛔ {codes}: hours outside the project's open period (closed, not opened or not in the global list). They are saved for analysis, but cannot be uploaded to Workday/N4W — to upload, move them to an active project in Outlook and read again.",
        "es": "⛔ {codes}: horas fuera de la vigencia del proyecto (cerrado, sin abrir o fuera de la base global). Quedan guardadas para análisis, pero no se pueden subir a Workday/N4W — para subirlas, pásalas a un proyecto activo en Outlook y vuelve a leer.",
        "pt": "⛔ {codes}: horas fora da vigência do projeto (encerrado, não aberto ou fora da base global). Ficam salvas para análise, mas não podem ser enviadas ao Workday/N4W — para enviar, passe-as para um projeto ativo no Outlook e leia de novo.",
    },
    "upload_blocked": {
        "en": "⛔ I can't upload these hours: {codes} have hours outside their open period. Correct the category of those meetings in Outlook and read again: “{phrase}”.",
        "es": "⛔ No puedo subir estas horas: {codes} tiene horas fuera de su vigencia. Corrige la categoría de esas reuniones en Outlook y vuelve a leer: “{phrase}”.",
        "pt": "⛔ Não posso enviar estas horas: {codes} tem horas fora da vigência. Corrija a categoria dessas reuniões no Outlook e leia de novo: “{phrase}”.",
    },
    "off_target": {
        "en": "⚠ Off your target dedication: {codes} (see the Projects card).",
        "es": "⚠ Fuera de tu dedicación objetivo: {codes} (ver la tarjeta Projects).",
        "pt": "⚠ Fora da sua dedicação alvo: {codes} (veja o cartão Projects).",
    },
    "new_projects": {
        "en": "ℹ New this month (no hours before): {codes}.",
        "es": "ℹ Nuevos este mes (sin horas antes): {codes}.",
        "pt": "ℹ Novos neste mês (sem horas antes): {codes}.",
    },
    "ask_target": {
        "en": "({i}/{n}) What should your dedication to {code} be? This month: {now}%, your average: {avg}. Answer “30%”, “40 h”, “same” (keeps {now}%) or “skip”.",
        "es": "({i}/{n}) ¿Cuál debería ser tu dedicación a {code}? Este mes: {now}%, tu promedio: {avg}. Responde “30%”, “40 h”, “igual” (deja {now}%) u “omitir”.",
        "pt": "({i}/{n}) Qual deveria ser sua dedicação a {code}? Este mês: {now}%, sua média: {avg}. Responda “30%”, “40 h”, “mesmo” (mantém {now}%) ou “pular”.",
    },
    "targets_later": {
        "en": "OK. You can set them anytime, e.g. “{phrase}”.",
        "es": "De acuerdo. Puedes fijarlas cuando quieras, p. ej. “{phrase}”.",
        "pt": "Certo. Você pode defini-las quando quiser, ex.: “{phrase}”.",
    },
    "ask_projects": {
        "en": "Before we start: which projects are you working on? Write their codes (e.g. “OF0104, FS3602A”) or, if you have your projects Excel, write “{phrase}” and pick the file. I'll check them against the global list.",
        "es": "Antes de empezar: ¿en qué proyectos estás trabajando? Escribe sus códigos (p. ej. “OF0104, FS3602A”) o, si tienes tu Excel de proyectos, escribe “{phrase}” y elige el archivo. Los verifico con la base global.",
        "pt": "Antes de começar: em quais projetos você está trabalhando? Escreva os códigos (ex.: “OF0104, FS3602A”) ou, se tiver sua planilha de projetos, escreva “{phrase}” e escolha o arquivo. Eu verifico na base global.",
    },
    "import_legacy": {
        "en": "I found your old projects Excel with {n} codes and checked them against the global list. Keep the ones you still work on.",
        "es": "Encontré tu Excel de proyectos antiguo con {n} códigos y los verifiqué con la base global. Deja marcados los que sigues trabajando.",
        "pt": "Encontrei sua planilha antiga de projetos com {n} códigos e verifiquei na base global. Deixe marcados os que você ainda trabalha.",
    },
    "import_failed": {
        "en": "⚠ I couldn't read {file} ({err}). It must have the “N4W-Projects” sheet with a “Code” column.",
        "es": "⚠ No pude leer {file} ({err}). Debe tener la hoja “N4W-Projects” con la columna “Code”.",
        "pt": "⚠ Não consegui ler {file} ({err}). Deve ter a aba “N4W-Projects” com a coluna “Code”.",
    },
    "import_empty": {
        "en": "{file} has no project codes to import.",
        "es": "{file} no tiene códigos de proyecto para importar.",
        "pt": "{file} não tem códigos de projeto para importar.",
    },
    "need_codes": {
        "en": "Which codes? Write them, e.g. “OF0104, FS3602A”.",
        "es": "¿Qué códigos? Escríbelos, p. ej. “OF0104, FS3602A”.",
        "pt": "Quais códigos? Escreva-os, ex.: “OF0104, FS3602A”.",
    },
    "codes_checked": {
        "en": "Checked against the global list: {details}.",
        "es": "Verificado con la base global: {details}.",
        "pt": "Verificado na base global: {details}.",
    },
    "frag_closed": {"en": "{code} is closed", "es": "{code} está cerrado", "pt": "{code} está encerrado"},
    "frag_missing": {"en": "{code} does not exist", "es": "{code} no existe", "pt": "{code} não existe"},
    "frag_already": {"en": "{code} is already in your list", "es": "{code} ya está en tu lista",
                     "pt": "{code} já está na sua lista"},
    "frag_not_mine": {"en": "{code} is not in your list", "es": "{code} no está en tu lista",
                      "pt": "{code} não está na sua lista"},
    "projects_added": {
        "en": "✓ Added to your projects: {codes}. {cats}",
        "es": "✓ Agregado a tus proyectos: {codes}. {cats}",
        "pt": "✓ Adicionado aos seus projetos: {codes}. {cats}",
    },
    "projects_removed": {
        "en": "✓ Removed from your projects: {codes}. Their Outlook categories are kept (your calendar stays intact).",
        "es": "✓ Quitado de tus proyectos: {codes}. Sus categorías de Outlook se mantienen (tu calendario queda intacto).",
        "pt": "✓ Removido dos seus projetos: {codes}. As categorias do Outlook são mantidas (seu calendário fica intacto).",
    },
    "projects_ready": {
        "en": "Your projects: {n}. You can change them anytime: “{a}” or “{b}”.",
        "es": "Tus proyectos: {n}. Puedes cambiarlos cuando quieras: “{a}” o “{b}”.",
        "pt": "Seus projetos: {n}. Você pode mudá-los quando quiser: “{a}” ou “{b}”.",
    },
    "review_intro": {
        "en": "I reviewed your projects and noticed: {details}. Shall I apply these changes? Untick what you want to keep as is.",
        "es": "Revisé tus proyectos y noté: {details}. ¿Aplico estos cambios? Desmarca lo que quieras dejar como está.",
        "pt": "Revisei seus projetos e notei: {details}. Aplico essas mudanças? Desmarque o que quiser manter como está.",
    },
    "frag_r_closed": {"en": "{code} was closed", "es": "{code} se cerró", "pt": "{code} foi encerrado"},
    "frag_r_missing": {"en": "{code} no longer exists in the global list",
                       "es": "{code} ya no existe en la base global",
                       "pt": "{code} não existe mais na base global"},
    "frag_r_idle": {"en": "you charged no hours to {code} in {months}",
                    "es": "no cargaste horas a {code} en {months}",
                    "pt": "você não lançou horas em {code} em {months}"},
    "frag_r_unlisted": {"en": "you charged {hours} to {code} but it is not in your list",
                        "es": "cargaste {hours} a {code} y no está en tu lista",
                        "pt": "você lançou {hours} em {code} e ele não está na sua lista"},
    "review_done": {
        "en": "✓ Done: {added} added, {removed} removed. You now have {n} projects.",
        "es": "✓ Listo: {added} agregado(s), {removed} quitado(s). Ahora tienes {n} proyectos.",
        "pt": "✓ Pronto: {added} adicionado(s), {removed} removido(s). Agora você tem {n} projetos.",
    },
    "review_kept": {
        "en": "OK, I left those as they are and won't suggest them again for {days} days.",
        "es": "De acuerdo, los dejo como están y no te lo vuelvo a sugerir en {days} días.",
        "pt": "Certo, deixo como estão e não sugiro de novo por {days} dias.",
    },
    "no_projects": {
        "en": "You have no projects in your list yet. Write their codes, e.g. “OF0104, FS3602A”.",
        "es": "Aún no tienes proyectos en tu lista. Escribe sus códigos, p. ej. “OF0104, FS3602A”.",
        "pt": "Você ainda não tem projetos na sua lista. Escreva os códigos, ex.: “OF0104, FS3602A”.",
    },
    "welcome": {
        "en": "Hi! I'm your timesheet assistant. We go one step at a time: read your hours from Outlook → prorate (when required) → fill Workday or submit N4W. Ask me about your hours and projects anytime, in any language. Suggestions appear as you type (Tab to accept).",
        "es": "¡Hola! Soy tu asistente de hojas de tiempo. Vamos paso a paso: leer tus horas de Outlook → prorratear (cuando aplica) → llenar Workday o enviar N4W. Pregúntame lo que quieras sobre tus horas y proyectos, en cualquier idioma. Mientras escribes verás sugerencias (Tab para aceptar).",
        "pt": "Olá! Sou seu assistente de timesheet. Vamos passo a passo: ler suas horas do Outlook → ratear (quando necessário) → preencher o Workday ou enviar N4W. Pergunte o que quiser sobre suas horas e projetos, em qualquer idioma. Sugestões aparecem enquanto você digita (Tab para aceitar).",
    },
    "start_examples": {
        "en": "To start, write for example: “{a}” or “{b}”.",
        "es": "Para empezar, escribe por ejemplo: “{a}” o “{b}”.",
        "pt": "Para começar, escreva por exemplo: “{a}” ou “{b}”.",
    },
    "also_ask": {
        "en": "You can also ask: “{a}” or “{b}”.",
        "es": "También puedes preguntar: “{a}” o “{b}”.",
        "pt": "Você também pode perguntar: “{a}” ou “{b}”.",
    },
}


def tr(key: str, lang: str, **kw) -> str:
    texts = MESSAGES[key]
    return texts.get(lang, texts["en"]).format(**kw)
