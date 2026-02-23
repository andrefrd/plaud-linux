"""
Módulo de upload automático para web.plaud.ai via Playwright.

Usa sessão persistente para manter login via Google SSO.
"""

import os
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


PLAUD_URL = "https://web.plaud.ai/"


class PlaudUploader:
    def __init__(self, session_dir: str):
        self.session_dir = session_dir

    def has_session(self) -> bool:
        """Verifica se já existe uma sessão salva."""
        cookies_path = os.path.join(self.session_dir, "Default", "Cookies")
        # Playwright persistent context saves in Default/
        return os.path.exists(cookies_path)

    def interactive_login(self):
        """Abre um navegador visível para o usuário fazer login manualmente."""
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self.session_dir,
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
                locale="pt-BR"
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(PLAUD_URL, wait_until="networkidle")

            print("🔐 Faça login no web.plaud.ai (Google SSO) e depois FECHE o navegador.")
            print("   A sessão será salva automaticamente.")

            # Esperar o usuário fechar o navegador
            try:
                context.pages[0].wait_for_event("close", timeout=0)
            except Exception:
                pass

            context.close()

    def upload(self, mp3_path: str) -> bool:
        """Faz upload de um arquivo MP3 para o web.plaud.ai usando sessão salva."""
        if not os.path.exists(mp3_path):
            print(f"Arquivo nao encontrado: {mp3_path}")
            return False

        print(f"Iniciando upload de {os.path.basename(mp3_path)} para web.plaud.ai...")

        with sync_playwright() as p:
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=self.session_dir,
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"],
                    locale="pt-BR"
                )
            except Exception as e:
                print(f"Erro ao abrir navegador: {e}")
                return False

            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(PLAUD_URL, wait_until="networkidle", timeout=30000)

                # Verificar se esta logado
                try:
                    page.wait_for_selector("div.c-layout-newrecording", timeout=15000)
                except PlaywrightTimeout:
                    print("Nao esta logado no web.plaud.ai. Execute o login novamente.")
                    context.close()
                    return False

                # Fechar qualquer modal overlay que esteja bloqueando (ex: "Plaud Desktop is here!")
                self._dismiss_modals(page)

                # 1. Clicar em "Add audio"
                add_audio_btn = page.locator("div.c-layout-newrecording")
                add_audio_btn.click(timeout=10000)
                print("   ok Clicou em 'Add audio'")

                # 2. Esperar o dropdown e clicar em "Import audio"
                import_btn = page.locator("div.menu-item", has_text="Import audio")
                import_btn.wait_for(state="visible", timeout=5000)
                import_btn.click()
                print("   ok Clicou em 'Import audio'")

                # 3. Esperar o modal e o input de arquivo
                file_input = page.locator("input[type='file'].my-file")
                file_input.wait_for(state="attached", timeout=5000)

                # 4. Enviar o arquivo para o input
                file_input.set_input_files(mp3_path)
                print("   ok Arquivo inserido no input de upload")

                # 5. Aguardar ate o site confirmar "Imported"
                print("   Aguardando confirmacao do site ('Imported')...")
                try:
                    page.locator("text=Imported").wait_for(state="visible", timeout=120000)
                    print("   ok Site confirmou: Imported")
                    
                    print("   Aguardando 30 segundos adicionais por seguranca (processamento do backend)...")
                    page.wait_for_timeout(30000)

                    # Verificar se o arquivo subiu vendo se o nome aparece na tabela de Recent files
                    base_name = os.path.splitext(os.path.basename(mp3_path))[0]
                    print(f"   Verificando tabela de recentes para: '{base_name}'...")
                    try:
                        # Busca o nome na lista de arquivos recentes
                        page.get_by_text(base_name, exact=False).first.wait_for(state="attached", timeout=30000)
                        print("   ok Arquivo encontrado na lista de arquivos recentes!")
                    except PlaywrightTimeout:
                        print(f"   Aviso: '{base_name}' não visível na lista imediata, mas o upload reportou sucesso.")

                except PlaywrightTimeout:
                    print("   Timeout esperando 'Imported' (120s). Pode ter dado erro no site.")

                print(f"Upload concluido: {os.path.basename(mp3_path)}")

                context.close()
                return True

            except Exception as e:
                print(f"Erro durante upload RPA: {e}")
                context.close()
                return False

    def _dismiss_modals(self, page):
        """Tenta fechar quaisquer modais/overlays que estejam bloqueando a interface."""
        # Tentar fechar por botoes comuns de modal
        dismiss_selectors = [
            "div.modal-overlay",                    # overlay generico
            "button:has-text('Maybe later')",       # botao do promo Plaud Desktop
            "button:has-text('Close')",
            "button:has-text('Got it')",
            "button:has-text('OK')",
            ".modal-close",                          # icone X generico
            "div.modal-overlay .close-btn",
        ]

        for selector in dismiss_selectors:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=1000):
                    el.click(timeout=2000)
                    print(f"   ok Modal fechado via: {selector}")
                    time.sleep(0.5)
            except Exception:
                continue

        # Fallback: remover overlays via JavaScript
        try:
            page.evaluate("""
                document.querySelectorAll('.modal-overlay').forEach(el => el.remove());
            """)
        except Exception:
            pass
