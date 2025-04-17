import tkinter as tk
from tkinter import ttk, messagebox
import os
import json
from datetime import datetime
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import urllib.parse
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import logging
import queue

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='download_manager.log'
)

def setup_driver(download_folder):
    """Configura o driver do Chrome para downloads automáticos"""
    chrome_options = Options()
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": download_folder,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def is_downloadable_link(url):
    """Verifica se o link é provavelmente um arquivo para download"""
    try:
        # Lista de extensões comuns para download
        download_extensions = {'.pdf', '.zip', '.rar', '.doc', '.docx', '.xls', '.xlsx', '.mp3', '.mp4', '.avi', '.mov'}
        
        # Verifica a extensão do arquivo na URL
        parsed = urllib.parse.urlparse(url)
        ext = os.path.splitext(parsed.path)[1].lower()
        
        # Se tem uma extensão conhecida, considera como downloadável
        if ext in download_extensions:
            return True
            
        return False
    except:
        return False

def get_download_filename(url):
    """Extrai o nome do arquivo da URL"""
    try:
        return os.path.basename(urllib.parse.urlparse(url).path)
    except:
        return "arquivo_desconhecido"

def is_already_downloaded(download_folder, filename):
    """Verifica se o arquivo já existe na pasta de downloads"""
    return os.path.exists(os.path.join(download_folder, filename))

def is_download_complete(download_folder, filename):
    """Verifica se o download foi concluído"""
    file_path = os.path.join(download_folder, filename)
    temp_path = os.path.join(download_folder, filename + '.crdownload')
    partial_path = os.path.join(download_folder, 'download.crdownload')
    
    # Espera até 30 segundos pelo download
    for _ in range(30):
        # Verifica se o arquivo final existe
        if os.path.exists(file_path):
            # Verifica se não está mais sendo modificado
            if not is_file_being_downloaded(file_path):
                return True
        # Verifica se existe algum arquivo temporário
        elif os.path.exists(temp_path) or os.path.exists(partial_path):
            time.sleep(1)
            continue
        # Se não encontrar nem arquivo temporário nem final, espera um pouco
        else:
            # Procura por arquivos .crdownload na pasta
            for f in os.listdir(download_folder):
                if f.endswith('.crdownload'):
                    time.sleep(1)
                    break
            else:
                # Se não encontrar nenhum .crdownload, espera um pouco mais
                time.sleep(1)
    return False

def is_file_being_downloaded(file_path):
    """Verifica se um arquivo ainda está sendo baixado"""
    try:
        # Tenta abrir o arquivo em modo exclusivo
        with open(file_path, 'ab') as f:
            return False
    except:
        return True

class DownloadManager:
    def __init__(self, root):
        """Inicializa o gerenciador de downloads"""
        try:
            self.root = root
            self.root.title("Gerenciador de Downloads")
            self.root.geometry("1200x800")
            
            # Inicializa variáveis antes de criar a interface
            self.stop_downloads = False
            self.download_queue = queue.Queue()
            self.downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads")
            self.history_file = os.path.join(self.downloads_folder, "download_history.json")
            self.download_history = []
            self.selected_links = set()
            self.update_pending = False
            self.last_update = 0
            self.update_interval = 100  # ms
            self.driver = None
            self.active_downloads = {}  # Armazena informações dos downloads ativos
            self.download_start_times = {}  # Armazena horário de início dos downloads

            # Inicia thread de monitoramento
            self.monitor_thread = threading.Thread(target=self.monitor_downloads, daemon=True)
            self.monitor_thread.start()

            # Configura a interface
            self.setup_frames()
            self.setup_controls()
            self.setup_trees()
            
            # Carrega o histórico após criar a interface
            self.load_history()
            
            # Configura manipuladores de eventos
            self.setup_event_handlers()
            
        except Exception as e:
            logging.error(f"Erro na inicialização: {str(e)}")
            messagebox.showerror("Erro", f"Erro ao iniciar o programa: {str(e)}")
            raise

    def setup_variables(self):
        """Inicializa variáveis e estados"""
        self.stop_downloads = False
        self.download_queue = queue.Queue()
        self.downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        self.history_file = os.path.join(self.downloads_folder, "download_history.json")
        self.download_history = []
        self.selected_links = set()
        self.update_pending = False
        self.last_update = 0
        self.update_interval = 100  # ms
        self.driver = None
        
        # Carregar histórico
        self.load_history()

    def setup_event_handlers(self):
        """Configura os manipuladores de eventos"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def on_closing(self):
        """Manipula o evento de fechamento da janela"""
        try:
            self.stop_downloads = True
            self.close_driver()
            self.root.destroy()
        except Exception as e:
            logging.error(f"Erro ao fechar o programa: {str(e)}")

    def setup_ui(self):
        """Configura a interface do usuário"""
        self.root.title("Gerenciador de Downloads")
        self.root.geometry("1000x800")
        
        # Configurar expansão da janela
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Configuração do estilo
        self.style = ttk.Style()
        self.style.configure("Treeview", rowheight=25)
        self.style.configure("Treeview.Heading", font=('Arial', 10, 'bold'))
        
        self.setup_frames()
        self.setup_controls()
        self.setup_trees()
        self.setup_status()
        
    def setup_frames(self):
        """Configura os frames principais"""
        try:
            # Frame principal
            self.main_frame = ttk.Frame(self.root, padding="10")
            self.main_frame.grid(row=0, column=0, sticky="nsew")
            
            # Configurar expansão do frame principal
            self.main_frame.grid_rowconfigure(3, weight=1)  # Links frame
            self.main_frame.grid_rowconfigure(4, weight=1)  # Selected items frame
            self.main_frame.grid_rowconfigure(6, weight=2)  # Downloads frame
            self.main_frame.grid_columnconfigure(0, weight=1)
            
            # Frame de controles principais
            self.control_frame = ttk.LabelFrame(self.main_frame, text="Configurações", padding="5")
            self.control_frame.grid(row=0, column=0, sticky="ew", pady=5)
            self.control_frame.grid_columnconfigure(1, weight=1)
            
            # Frame de botões
            self.button_frame = ttk.Frame(self.main_frame)
            self.button_frame.grid(row=1, column=0, sticky="ew", pady=5)
            
            # Frame de links
            self.links_frame = ttk.LabelFrame(self.main_frame, text="Links Encontrados", padding="5")
            self.links_frame.grid(row=3, column=0, sticky="nsew", pady=5)
            self.links_frame.grid_rowconfigure(0, weight=1)
            self.links_frame.grid_columnconfigure(0, weight=1)
            
            # Frame de itens selecionados
            self.selected_frame = ttk.LabelFrame(self.main_frame, text="Itens Selecionados", padding="5")
            self.selected_frame.grid(row=4, column=0, sticky="nsew", pady=5)
            self.selected_frame.grid_rowconfigure(0, weight=1)
            self.selected_frame.grid_columnconfigure(0, weight=1)
            
            # Frame do histórico
            self.history_header_frame = ttk.Frame(self.main_frame)
            self.history_header_frame.grid(row=5, column=0, sticky="ew", pady=(10,0))
            
            self.downloads_frame = ttk.LabelFrame(self.main_frame, text="Histórico de Downloads", padding="5")
            self.downloads_frame.grid(row=6, column=0, sticky="nsew", pady=5)
            self.downloads_frame.grid_rowconfigure(0, weight=1)
            self.downloads_frame.grid_columnconfigure(0, weight=1)
            
            # Frame de progresso total
            self.progress_frame = ttk.LabelFrame(self.main_frame, text="Progresso Total", padding="5")
            self.progress_frame.grid(row=7, column=0, sticky="ew", pady=5)
            
            # Configurar expansão da janela principal
            self.root.grid_rowconfigure(0, weight=1)
            self.root.grid_columnconfigure(0, weight=1)
            
        except Exception as e:
            logging.error(f"Erro ao configurar frames: {str(e)}")
            raise

    def setup_controls(self):
        """Configura os controles da interface"""
        # URL
        ttk.Label(self.control_frame, text="URL:").grid(row=0, column=0, padx=(0, 5), sticky="w")
        self.url_entry = ttk.Entry(self.control_frame)
        self.url_entry.grid(row=0, column=1, columnspan=3, sticky="ew", padx=5, pady=2)
        
        # Email e Senha
        ttk.Label(self.control_frame, text="Email:").grid(row=1, column=0, padx=(0, 5), sticky="w")
        self.email_entry = ttk.Entry(self.control_frame)
        self.email_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        
        ttk.Label(self.control_frame, text="Senha:").grid(row=1, column=2, padx=5, sticky="w")
        self.password_entry = ttk.Entry(self.control_frame, show="*")
        self.password_entry.grid(row=1, column=3, sticky="ew", padx=5, pady=2)
        
        # Downloads Simultâneos
        ttk.Label(self.control_frame, text="Downloads Simultâneos:").grid(row=2, column=0, padx=(0, 5), sticky="w")
        self.max_downloads_var = tk.StringVar(value="3")
        self.max_downloads_spinbox = ttk.Spinbox(
            self.control_frame,
            from_=1,
            to=10,
            width=5,
            textvariable=self.max_downloads_var
        )
        self.max_downloads_spinbox.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        
        # Botões principais
        self.refresh_button = ttk.Button(self.button_frame, text="Buscar Links", command=self.search_links)
        self.refresh_button.pack(side="left", padx=5)
        
        self.start_button = ttk.Button(self.button_frame, text="Iniciar Downloads", command=self.start_downloads)
        self.start_button.pack(side="left", padx=5)
        
        self.stop_button = ttk.Button(self.button_frame, text="Parar Downloads", 
                                    command=self.stop_downloads_action, state="disabled")
        self.stop_button.pack(side="left", padx=5)
        
        # Botão de limpar histórico
        self.clear_history_button = ttk.Button(self.history_header_frame, text="Limpar Histórico", command=self.clear_history)
        self.clear_history_button.pack(side="right", padx=5)
        
        # Barra de progresso total
        self.progress = ttk.Progressbar(self.progress_frame, mode='determinate')
        self.progress.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.status_label = ttk.Label(self.progress_frame, text="Pronto")
        self.status_label.grid(row=1, column=0, sticky="w", padx=5)
        
    def setup_trees(self):
        """Configura as TreeViews"""
        # Links TreeView
        links_container = ttk.Frame(self.links_frame)
        links_container.grid(row=0, column=0, sticky="nsew")
        links_container.grid_rowconfigure(0, weight=1)
        links_container.grid_columnconfigure(0, weight=1)
        
        self.links_tree = ttk.Treeview(links_container, columns=("Selecionar", "Link", "Tipo"), 
                                     show="headings")
        self.setup_tree_columns(self.links_tree, [
            ("Selecionar", 100),
            ("Link", 400),
            ("Tipo", 100)
        ])
        self.links_tree.grid(row=0, column=0, sticky="nsew")
        
        # Scrollbars para links
        links_vsb = ttk.Scrollbar(links_container, orient="vertical", command=self.links_tree.yview)
        links_vsb.grid(row=0, column=1, sticky="ns")
        links_hsb = ttk.Scrollbar(links_container, orient="horizontal", command=self.links_tree.xview)
        links_hsb.grid(row=1, column=0, sticky="ew")
        self.links_tree.configure(yscrollcommand=links_vsb.set, xscrollcommand=links_hsb.set)
        
        # Selected Items TreeView
        selected_container = ttk.Frame(self.selected_frame)
        selected_container.grid(row=0, column=0, sticky="nsew")
        selected_container.grid_rowconfigure(0, weight=1)
        selected_container.grid_columnconfigure(0, weight=1)
        
        self.selected_tree = ttk.Treeview(selected_container, 
                                        columns=("Nome", "Progresso", "Status"),
                                        show="headings")
        self.setup_tree_columns(self.selected_tree, [
            ("Nome", 400),
            ("Progresso", 200),
            ("Status", 100)
        ])
        self.selected_tree.grid(row=0, column=0, sticky="nsew")
        
        # Scrollbars para itens selecionados
        selected_vsb = ttk.Scrollbar(selected_container, orient="vertical", command=self.selected_tree.yview)
        selected_vsb.grid(row=0, column=1, sticky="ns")
        selected_hsb = ttk.Scrollbar(selected_container, orient="horizontal", command=self.selected_tree.xview)
        selected_hsb.grid(row=1, column=0, sticky="ew")
        self.selected_tree.configure(yscrollcommand=selected_vsb.set, xscrollcommand=selected_hsb.set)
        
        # Downloads TreeView
        downloads_container = ttk.Frame(self.downloads_frame)
        downloads_container.grid(row=0, column=0, sticky="nsew")
        downloads_container.grid_rowconfigure(0, weight=1)
        downloads_container.grid_columnconfigure(0, weight=1)
        
        self.tree = ttk.Treeview(downloads_container, 
                                columns=("Nome", "Status", "Data", "Tamanho"),
                                show="headings")
        self.setup_tree_columns(self.tree, [
            ("Nome", 300),
            ("Status", 100),
            ("Data", 150),
            ("Tamanho", 100)
        ])
        self.tree.grid(row=0, column=0, sticky="nsew")
        
        # Scrollbars para downloads
        downloads_vsb = ttk.Scrollbar(downloads_container, orient="vertical", command=self.tree.yview)
        downloads_vsb.grid(row=0, column=1, sticky="ns")
        downloads_hsb = ttk.Scrollbar(downloads_container, orient="horizontal", command=self.tree.xview)
        downloads_hsb.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=downloads_vsb.set, xscrollcommand=downloads_hsb.set)
        
        # Bindings
        self.links_tree.bind('<ButtonRelease-1>', self.on_tree_click)

    def setup_tree_columns(self, tree, columns):
        """Configura colunas para uma TreeView"""
        for col, width in columns:
            tree.heading(col, text=col)
            tree.column(col, width=width)
            
    def setup_status(self):
        """Configura a barra de status e progresso"""
        self.status_label = ttk.Label(self.status_frame, text="Pronto")
        self.status_label.grid(row=0, column=0, sticky="w")
        
        self.progress = ttk.Progressbar(self.status_frame, mode='determinate')
        self.progress.grid(row=0, column=1, sticky="ew", padx=5)
        
    def schedule_ui_update(self):
        """Agenda atualização da interface se necessário"""
        if not self.update_pending:
            current_time = time.time() * 1000
            if current_time - self.last_update >= self.update_interval:
                def update():
                    self.refresh_downloads()
                self.root.after(0, update)
                self.last_update = current_time
                self.update_pending = False
            else:
                self.root.after(self.update_interval, self.schedule_ui_update)
                self.update_pending = True

    def safe_ui_call(self, func, *args, **kwargs):
        """Executa uma função na thread principal de forma segura"""
        if threading.current_thread() is threading.main_thread():
            return func(*args, **kwargs)
        else:
            return self.root.after(0, lambda: func(*args, **kwargs))
            
    def update_status(self, message):
        """Atualiza o status de forma segura"""
        def update():
            self.status_label.config(text=message)
        self.safe_ui_call(update)
        
    def update_progress(self, value):
        """Atualiza a barra de progresso de forma segura"""
        def update():
            self.progress['value'] = value
        self.safe_ui_call(update)

    def on_tree_click(self, event):
        """Manipula cliques na treeview de links"""
        item = self.links_tree.identify_row(event.y)
        if item:
            col = self.links_tree.identify_column(event.x)
            if col == "#1":  # Coluna de seleção
                values = self.links_tree.item(item, 'values')
                if values:
                    link = values[2]  # URL do link
                    if link in self.selected_links:
                        self.selected_links.remove(link)
                        self.links_tree.item(item, values=("☐", values[1], link))
                        self.remove_from_selected_tree(link)
                    else:
                        self.selected_links.add(link)
                        self.links_tree.item(item, values=("☑", values[1], link))
                        self.add_to_selected_tree(values[1], link)

    def add_to_selected_tree(self, name, link):
        """Adiciona um item à árvore de selecionados"""
        self.selected_tree.insert("", "end", values=(name, "0%", "Pendente"), tags=(link,))

    def remove_from_selected_tree(self, link):
        """Remove um item da árvore de selecionados"""
        for item in self.selected_tree.get_children():
            if link in self.selected_tree.item(item)["tags"]:
                self.selected_tree.delete(item)
                break

    def update_selected_progress(self, link, progress, status):
        """Atualiza o progresso de um item selecionado"""
        for item in self.selected_tree.get_children():
            if link in self.selected_tree.item(item)["tags"]:
                self.selected_tree.item(item, values=(
                    self.selected_tree.item(item)["values"][0],
                    f"{progress}%",
                    status
                ))
                break

    def load_history(self):
        """Carrega o histórico de downloads do arquivo JSON"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.download_history = json.load(f)
                    # Atualiza entradas antigas que não têm display_name
                    for entry in self.download_history:
                        if "display_name" not in entry:
                            entry["display_name"] = entry["filename"]
            else:
                self.download_history = []
        except Exception as e:
            self.download_history = []
            logging.error(f"Erro ao carregar histórico: {str(e)}")
            messagebox.showerror("Erro", f"Erro ao carregar histórico: {str(e)}")
        
        # Atualiza a interface com o histórico
        self.refresh_downloads()
    
    def save_history(self):
        """Salva o histórico de downloads no arquivo JSON"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.download_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar histórico: {str(e)}")
    
    def refresh_downloads(self):
        """Atualiza a lista de downloads na interface"""
        try:
            # Limpar a treeview
            if hasattr(self, 'tree'):
                for item in self.tree.get_children():
                    self.tree.delete(item)
                
                # Adicionar downloads do histórico
                for download in self.download_history:
                    self.tree.insert("", "end", values=(
                        download.get("display_name", download["filename"]),
                        download["status"],
                        download["date"],
                        download.get("size", "N/A")
                    ))
        except Exception as e:
            logging.error(f"Erro ao atualizar lista de downloads: {str(e)}")
    
    def search_links(self):
        """Busca links na URL fornecida"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Aviso", "Por favor, insira uma URL válida")
            return
            
        try:
            self.status_label.config(text="Buscando links...")
            self.refresh_button.config(state="disabled")
            
            # Limpa a lista de links atual
            for item in self.links_tree.get_children():
                self.links_tree.delete(item)
            
            # Inicializa o driver se necessário
            if not self.driver:
                self.driver = self.setup_driver()
            
            # Tenta fazer login se necessário
            login_result = self.login(self.driver, url)
            if not login_result and (self.email_entry.get().strip() or self.password_entry.get().strip()):
                messagebox.showwarning("Aviso", "Não foi possível fazer login. Alguns links podem não estar disponíveis.")
            
            # Navega para a URL
            self.driver.get(url)
            
            # Espera página carregar
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Tenta rolar a página para carregar mais conteúdo
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            while True:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            
            # Encontrar todos os links
            links = self.driver.find_elements(By.TAG_NAME, "a")
            found_links = 0
            
            # Adicionar links encontrados
            for link in links:
                href = link.get_attribute("href")
                if href and not href.startswith("mailto:"):
                    link_text = link.text.strip() or "Link sem texto"
                    if is_downloadable_link(href):
                        self.links_tree.insert("", "end", values=("☐", link_text, href))
                        found_links += 1
            
            if found_links == 0:
                self.status_label.config(text="Nenhum link de download encontrado")
            else:
                self.status_label.config(text=f"{found_links} links de download encontrados")
            
        except Exception as e:
            logging.error(f"Erro ao buscar links: {str(e)}")
            messagebox.showerror("Erro", f"Erro ao buscar links: {str(e)}")
            self.status_label.config(text="Erro ao buscar links")
        
        finally:
            self.refresh_button.config(state="normal")

    def start_downloads(self):
        """Inicia o processo de download"""
        if not self.selected_links:
            messagebox.showwarning("Aviso", "Por favor, selecione pelo menos um link para download")
            return
            
        self.status_label.config(text="Iniciando downloads...")
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.stop_downloads = False
        
        # Iniciar download em uma thread separada
        thread = threading.Thread(target=self.run_downloads, args=(self.url_entry.get().strip(),))
        thread.daemon = True
        thread.start()
    
    def stop_downloads_action(self):
        """Ação para parar os downloads"""
        self.stop_downloads = True
        self.status_label.config(text="Parando downloads...")
        self.stop_button.config(state="disabled")
        self.close_driver()
    
    def run_downloads(self, url):
        """Executa o processo de download e atualiza a interface"""
        try:
            total_links = len(self.selected_links)
            downloaded = 0
            skipped = 0
            failed = 0
            
            self.progress['maximum'] = total_links
            self.update_progress(0)
            
            try:
                max_concurrent = min(max(1, int(self.max_downloads_var.get())), 10)
            except:
                max_concurrent = 3
            
            if not self.driver:
                self.driver = self.setup_driver()

            try:
                with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
                    futures = []
                    
                    for link in self.selected_links:
                        if self.stop_downloads:
                            break
                        
                        future = executor.submit(self.process_single_download, link)
                        futures.append(future)
                        
                        active_downloads = len([f for f in futures if not f.done()])
                        self.update_status(f"Downloads ativos: {active_downloads} / {max_concurrent}")
                        
                        time.sleep(0.5)
                    
                    for future in futures:
                        try:
                            result = future.result()
                            if result == "downloaded":
                                downloaded += 1
                            elif result == "skipped":
                                skipped += 1
                            else:
                                failed += 1
                                
                            self.update_progress(downloaded + skipped + failed)
                            self.schedule_ui_update()
                            
                            active_downloads = len([f for f in futures if not f.done()])
                            self.update_status(f"Downloads ativos: {active_downloads} / {max_concurrent}")
                            
                        except Exception as e:
                            failed += 1
                            logging.error(f"Erro no download: {str(e)}")
                            
            finally:
                if self.stop_downloads:
                    self.close_driver()
            
            self.save_history()
            self.update_interface(downloaded, skipped, failed)
            
        except Exception as e:
            logging.error(f"Erro durante downloads: {str(e)}")
            self.show_error(str(e))
            self.close_driver()

    def process_single_download(self, link):
        """Processa um único download"""
        try:
            # Encontrar o nome legível do link na árvore de links
            link_text = None
            for item in self.links_tree.get_children():
                values = self.links_tree.item(item)['values']
                if values[2] == link:  # values[2] contém a URL
                    link_text = values[1]  # values[1] contém o texto do link
                    break
            
            filename = get_download_filename(link)
            display_name = link_text if link_text else filename
            
            # Verificar se já existe
            if is_already_downloaded(self.downloads_folder, filename):
                self.download_history.append({
                    "filename": filename,
                    "display_name": display_name,
                    "status": "Já existente",
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "size": self.get_file_size(filename)
                })
                return "skipped"
            
            # Adicionar entrada inicial no histórico
            download_entry = {
                "filename": filename,
                "display_name": display_name,
                "status": "Baixando...",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "size": "N/A"
            }
            self.download_history.append(download_entry)
            self.save_history()
            self.refresh_downloads()
            
            try:
                # Registra início do download
                self.active_downloads[filename] = {
                    'url': link,
                    'display_name': display_name,
                    'status': 'Iniciando...'
                }
                self.download_start_times[filename] = time.time()
                
                # Usar o driver compartilhado para fazer o download
                self.driver.get(link)
                
                # Esperar download completar
                if is_download_complete(self.downloads_folder, filename):
                    download_entry["status"] = "Concluído"
                    download_entry["size"] = self.get_file_size(filename)
                    # Remove do monitoramento
                    if filename in self.active_downloads:
                        del self.active_downloads[filename]
                    if filename in self.download_start_times:
                        del self.download_start_times[filename]
                    return "downloaded"
                else:
                    download_entry["status"] = "Erro no download"
                    return "failed"
                    
            except Exception as e:
                download_entry["status"] = f"Erro: {str(e)}"
                return "failed"
                
        except Exception as e:
            print(f"Erro ao processar download de {link}: {str(e)}")
            return "failed"
    
    def get_file_size(self, filename):
        """Retorna o tamanho do arquivo em formato legível"""
        try:
            file_path = os.path.join(self.downloads_folder, filename)
            if os.path.exists(file_path):
                size = os.path.getsize(file_path)
                if size < 1024:
                    return f"{size} B"
                elif size < 1024 * 1024:
                    return f"{size/1024:.1f} KB"
                elif size < 1024 * 1024 * 1024:
                    return f"{size/(1024*1024):.1f} MB"
                else:
                    return f"{size/(1024*1024*1024):.1f} GB"
            return "N/A"
        except:
            return "N/A"

    def show_error(self, error_message):
        """Mostra mensagem de erro de forma segura"""
        def show():
            messagebox.showerror("Erro", error_message)
            self.status_label.config(text="Erro durante os downloads")
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
        self.safe_ui_call(show)

    def update_interface(self, downloaded, skipped, failed):
        """Atualiza a interface após os downloads"""
        def update():
            self.refresh_downloads()
            self.status_label.config(text=f"Downloads concluídos: {downloaded} | Ignorados: {skipped} | Falhas: {failed}")
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
        self.safe_ui_call(update)

    def clear_history(self):
        """Limpa o histórico de downloads"""
        if messagebox.askyesno("Confirmar", "Tem certeza que deseja limpar todo o histórico de downloads?"):
            # Limpa apenas o histórico de downloads
            self.download_history = []
            self.save_history()
            
            # Limpa apenas a árvore de histórico de downloads
            for item in self.tree.get_children():
                self.tree.delete(item)
                
            self.status_label.config(text="Histórico de downloads limpo")

    def setup_driver(self):
        """Configura o driver do Chrome com opções otimizadas"""
        chrome_options = Options()
        chrome_options.add_experimental_option("prefs", {
            "download.default_directory": self.downloads_folder,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        })
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")
        
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=chrome_options)

    def login(self, driver, url):
        """Tenta fazer login no site se as credenciais forem fornecidas"""
        try:
            email = self.email_entry.get().strip()
            password = self.password_entry.get().strip()
            
            # Se não houver credenciais, assume que não precisa de login
            if not email and not password:
                logging.info("Nenhuma credencial fornecida, tentando acessar diretamente")
                return True

            # Tenta encontrar o formulário de login
            driver.get(url)
            time.sleep(2)  # Espera a página carregar
            
            # Procura por campos de login comuns
            email_fields = driver.find_elements(By.CSS_SELECTOR, 'input[type="email"], input[name="email"]')
            password_fields = driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]')
            submit_buttons = driver.find_elements(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]')
            
            if email_fields and password_fields and submit_buttons:
                email_fields[0].send_keys(email)
                password_fields[0].send_keys(password)
                submit_buttons[0].click()
                time.sleep(3)  # Espera o login processar
                return True
            
            return True  # Retorna True se não encontrar formulário de login
            
        except Exception as e:
            logging.error(f"Erro ao tentar fazer login: {str(e)}")
            return False

    def close_driver(self):
        """Fecha o driver do Chrome de forma segura"""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
        except Exception as e:
            logging.error(f"Erro ao fechar driver: {str(e)}")

    def __del__(self):
        """Destrutor da classe"""
        self.close_driver()

    def monitor_downloads(self):
        """Monitora o progresso dos downloads ativos"""
        while True:
            try:
                if self.stop_downloads:
                    break

                # Lista todos os arquivos .crdownload na pasta de downloads
                crdownload_files = [f for f in os.listdir(self.downloads_folder) if f.endswith('.crdownload')]
                
                # Atualiza o progresso para cada item selecionado
                for item in self.selected_tree.get_children():
                    values = self.selected_tree.item(item)["values"]
                    tags = self.selected_tree.item(item)["tags"]
                    if not tags:
                        continue
                        
                    url = tags[0]
                    filename = get_download_filename(url)
                    file_path = os.path.join(self.downloads_folder, filename)
                    temp_path = file_path + '.crdownload'
                    
                    # Verifica se o arquivo já foi completamente baixado
                    if os.path.exists(file_path):
                        self.selected_tree.item(item, values=(values[0], "100%", "Concluído"))
                        continue
                        
                    # Verifica se o arquivo está sendo baixado
                    if os.path.exists(temp_path):
                        try:
                            temp_size = os.path.getsize(temp_path)
                            # Tenta ler o tamanho total do arquivo do .crdownload
                            with open(temp_path, 'rb') as f:
                                f.seek(-8, 2)  # O Chrome armazena o tamanho total no final do arquivo
                                total_size = int.from_bytes(f.read(8), byteorder='little')
                                
                            if total_size > 0:
                                progress = int((temp_size / total_size) * 100)
                                self.selected_tree.item(item, values=(
                                    values[0],
                                    f"{progress}%",
                                    f"Baixando - {self.format_size(temp_size)}/{self.format_size(total_size)}"
                                ))
                            else:
                                self.selected_tree.item(item, values=(values[0], "0%", "Iniciando..."))
                        except:
                            self.selected_tree.item(item, values=(values[0], "0%", "Calculando..."))
                    elif filename not in [f[:-10] for f in crdownload_files]:  # Verifica se não há download em andamento
                        if values[2] != "Concluído" and values[2] != "Erro":
                            self.selected_tree.item(item, values=(values[0], "0%", "Pendente"))

                time.sleep(0.5)  # Evita uso excessivo de CPU
                
            except Exception as e:
                logging.error(f"Erro no monitoramento: {str(e)}")
                time.sleep(1)

    def format_size(self, size):
        """Formata o tamanho do arquivo"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def format_time(self, seconds):
        """Formata o tempo restante"""
        if seconds < 60:
            return f"{int(seconds)} segundos"
        elif seconds < 3600:
            return f"{int(seconds/60)} minutos"
        else:
            hours = int(seconds/3600)
            minutes = int((seconds % 3600)/60)
            return f"{hours}h {minutes}m"

    def get_total_size(self, filename):
        """Tenta obter o tamanho total do arquivo"""
        try:
            file_path = os.path.join(self.downloads_folder, filename)
            temp_path = file_path + '.crdownload'
            
            # Tenta ler o tamanho do arquivo temporário
            if os.path.exists(temp_path):
                with open(temp_path, 'rb') as f:
                    f.seek(-8, 2)  # Chrome stores file size at the end
                    return int.from_bytes(f.read(8), byteorder='little')
            
            # Se o arquivo já existe, usa seu tamanho
            if os.path.exists(file_path):
                return os.path.getsize(file_path)
                
        except:
            pass
        return None

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = DownloadManager(root)
        root.mainloop()
    except Exception as e:
        logging.error(f"Erro fatal: {str(e)}")
        if 'root' in locals() and root:
            root.destroy() 