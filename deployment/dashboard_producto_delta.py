import sys
import os

# --- INICIO DEL CÓDIGO DE RESOLUCIÓN DE PATH ---

# Obtener la ruta absoluta del directorio donde se encuentra este script (la carpeta 'deployment')
current_dir = os.path.dirname(os.path.abspath(__file__))

# Subir un nivel para obtener la ruta del directorio raíz del proyecto ('scraper_meli')
project_root = os.path.dirname(current_dir)

# Añadir el directorio raíz al sys.path de Python
# Esto le permite a Python "ver" todas las carpetas del proyecto, como 'reporting'
if project_root not in sys.path:
    sys.path.insert(0, project_root)


# Ahora que el proyecto raíz está en el path, este import ABSOLUTO funciona perfectamente
from reporting.dashboard_micro import run_dashboard


if __name__ == "__main__":
    run_dashboard()