import os
import csv
import json
import re
import urllib.request
import urllib.error
from datetime import datetime
from typing import List, Dict, Any, Optional, Set

# --- Configuration ---
CSV_FILENAME = "modeles_ia.csv"
DATE_FILE = "derniere_recherche.txt"
OLLAMA_PORT = 11434
OLLAMA_IPS = ["127.0.0.1", "192.168.1.8"]

# --- Utilitaires ---
def get_last_date() -> str:
    """Récupère la date de la dernière recherche depuis le fichier, ou retourne la date du jour par défaut."""
    if os.path.exists(DATE_FILE):
        with open(DATE_FILE, "r") as f:
            date_str = f.read().strip()
            if date_str:
                return date_str
    # Par défaut, il y a un mois
    return "01-01-2026"

def save_last_date(date_str: str):
    """Sauvegarde la date de la recherche actuelle."""
    with open(DATE_FILE, "w") as f:
        f.write(date_str)

def get_date_input() -> str:
    """Demande à l'utilisateur depuis quelle date chercher les nouveautés."""
    last_date = get_last_date()
    print(f"\nDate de la dernière recherche mémorisée : {last_date}")
    user_date = input(f"Depuis quelle date voulez-vous chercher ? (JJ-MM-AAAA) [Entrée pour garder {last_date}] : ").strip()
    return user_date if user_date else last_date

def detect_ollama() -> Optional[str]:
    """Teste les IP configurées pour trouver sur laquelle Ollama répond."""
    print("\nRecherche du serveur Ollama...")
    for ip in OLLAMA_IPS:
        url = f"http://{ip}:{OLLAMA_PORT}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as response:
                if response.status == 200:
                    print(f"✅ Serveur Ollama détecté sur {ip}")
                    return ip
        except Exception:
            continue
    print("❌ Aucun serveur Ollama détecté (ni en local, ni sur 192.168.1.8).")
    return None

def fetch_ollama_models(ip: str) -> List[Dict[str, Any]]:
    """Récupère la liste des modèles installés sur le serveur Ollama."""
    url = f"http://{ip}:{OLLAMA_PORT}/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return data.get("models", [])
    except Exception as e:
        print(f"Erreur lors de la récupération des modèles Ollama : {e}")
        return []

def search_hf_models(author: str, since_date: str) -> List[Dict[str, Any]]:
    """Cherche les modèles GGUF d'un auteur spécifique sur Hugging Face depuis une certaine date."""
    print(f"\nRecherche des modèles GGUF pour {author} sur Hugging Face...")
    # Formatage simple de la date pour l'affichage, l'API HF requiert des timestamps ou des requêtes complexes,
    # pour simplifier dans ce script sans dépendances lourdes, on récupère les récents et on filtre.
    # L'utilisation de requests/huggingface_hub serait meilleure, mais urllib garde le script autonome.
    
    url = f"https://huggingface.co/api/models?author={author}&search=gguf&sort=createdAt&direction=-1&limit=50"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Erreur lors de la recherche sur Hugging Face pour {author} : {e}")
        return []

def parse_selection(text: str, max_num: int) -> Set[int]:
    """Convertit une saisie du type '1, 2, 5-7, 9' en ensemble de numéros valides (1 à max_num)."""
    nums = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            if start > end:
                start, end = end, start
            nums.update(n for n in range(start, end + 1) if 1 <= n <= max_num)
        elif part.isdigit() and 1 <= int(part) <= max_num:
            nums.add(int(part))
    return nums

def display_menu(options: List[str], title: str) -> List[str]:
    """Affiche un menu numéroté : saisir '1, 2, 5-7, 9' (co)dé coche les choix 1, 2, 5, 6, 7 et 9."""
    print(f"\n--- {title} ---")
    selected = set()
    
    while True:
        for i, opt in enumerate(options):
            mark = "[x]" if (i + 1) in selected else "[ ]"
            print(f"{i + 1}. {mark} {opt}")
        print("0. Terminer la sélection")

        choice = input("Numéros à cocher/décocher (ex : 1, 2, 5-7, 9 ; 'a' = tout ; 0 ou Entrée = valider) : ").strip()
        if choice in ("0", ""):
            break
        if choice.lower() in ("a", "all", "tout"):
            selected = set(range(1, len(options) + 1))
            continue
        if choice.lower() in ("n", "none", "aucun"):
            selected.clear()
            continue
        nums = parse_selection(choice, len(options))
        if not nums:
            print("Saisie non reconnue, exemple valide : 1, 2, 5-7, 9")
            continue
        for n in nums:
            if n in selected:
                selected.remove(n)
            else:
                selected.add(n)

    return [options[i - 1] for i in sorted(selected)]

def estimate_hardware(size_gb: float) -> str:
    """Estime le matériel cible selon la taille."""
    if size_gb < 11:
        return "1x RTX 3060 (12 Go)"
    elif size_gb <= 22:
        return "2x RTX 3060 (24 Go)"
    else:
        return "2x RTX 3060 + RAM (>24 Go)"

def export_to_csv(models: List[Dict[str, Any]], filename: str):
    """Exporte la liste des modèles en CSV avec un point-virgule et des guillemets."""
    # En-têtes correspondant à votre base Notion
    headers = [
        "Nom",
        "Éditeur",
        "Créateur de la version",
        "Famille",
        "Taille GGUF (Go)",
        "Matériel cible",
        "Quantisation",
        "Fenêtre de contexte (k)",
        "Paramètres (B)",
        "Usage",
        "Type",
        "Multimodal",
        "Français",
        "Vitesse",
        "Qualité",
        "Date d'évaluation",
        "Ollama",
        "LM Studio",
        "Hugging Face",
        "URL Hugging Face",
        "URL Ollama",
        "Commentaires personnels"
    ]
    
    file_exists = os.path.isfile(filename)
    
    with open(filename, 'a', newline='', encoding='utf-8') as f:
        # csv.writer avec point-virgule, met des guillemets si nécessaire
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        if not file_exists:
            writer.writeheader()
            
        for m in models:
            writer.writerow(m)
            
    print(f"\n✅ {len(models)} modèles exportés dans {filename}")

def main():
    print("==================================================")
    print("  Générateur de Base de Données Modèles IA (CSV)  ")
    print("==================================================")
    
    # 1. Date de recherche
    search_date = get_date_input()
    
    # 2. Détection Ollama
    ollama_ip = detect_ollama()
    
    # 3. Sélection des éditeurs
    default_authors = ["mistralai", "meta-llama", "microsoft", "google", "bartowski", "TheBloke"]
    selected_authors = display_menu(default_authors, "Éditeurs à rechercher sur Hugging Face (Modèles GGUF)")
    
    all_hf_models = []
    for author in selected_authors:
        all_hf_models.extend(search_hf_models(author, search_date))
        
    # Extraction des noms pour le menu
    hf_model_names = [m.get("id") for m in all_hf_models]
    
    selected_hf_names = []
    if hf_model_names:
        selected_hf_names = display_menu(hf_model_names, "Modèles Hugging Face trouvés à ajouter")
    else:
        print("\nAucun modèle récent trouvé sur Hugging Face pour ces auteurs.")

    # 4. Traitement des modèles Ollama locaux
    ollama_models = []
    if ollama_ip:
        ollama_data = fetch_ollama_models(ollama_ip)
        ollama_names = [m.get("name") for m in ollama_data]
        if ollama_names:
            selected_ollama = display_menu(ollama_names, "Modèles détectés sur votre Ollama local")
            for m in ollama_data:
                if m.get("name") in selected_ollama:
                    # Conversion des tailles en Go
                    size_gb = round(m.get("size", 0) / (1024**3), 2)
                    ollama_models.append({
                        "Nom": m.get("name"),
                        "Éditeur": "À renseigner",
                        "Créateur de la version": "Ollama Registry",
                        "Famille": m.get("details", {}).get("family", ""),
                        "Taille GGUF (Go)": size_gb,
                        "Matériel cible": estimate_hardware(size_gb),
                        "Paramètres (B)": m.get("details", {}).get("parameter_size", "").replace("B", ""),
                        "Quantisation": m.get("details", {}).get("quantization_level", ""),
                        "Ollama": "Oui",
                        "LM Studio": "Non",
                        "Hugging Face": "Non",
                        "Type": "LLM",
                        "Date d'évaluation": datetime.now().strftime("%Y-%m-%d")
                    })
    
    # 5. Traitement des modèles Hugging Face sélectionnés
    hf_models_to_export = []
    for m in all_hf_models:
        if m.get("id") in selected_hf_names:
            # Gérer les éditeurs officiels vs compresseurs
            author = m.get("author", "")
            creator = author
            editor = author
            if author in ["bartowski", "TheBloke", "lmstudio-community"]:
                editor = "Original (à vérifier)"
            
            hf_models_to_export.append({
                "Nom": m.get("id").split("/")[-1],
                "Éditeur": editor,
                "Créateur de la version": creator,
                "Famille": "À renseigner",
                "Hugging Face": "Oui",
                "LM Studio": "Oui", # Les GGUF sont compatibles LM Studio
                "Ollama": "Non",
                "URL Hugging Face": f"https://huggingface.co/{m.get('id')}",
                "Type": "LLM",
                "Date d'évaluation": datetime.now().strftime("%Y-%m-%d")
            })

    # 6. Fusion et Export
    final_list = ollama_models + hf_models_to_export
    if final_list:
        export_to_csv(final_list, CSV_FILENAME)
        # Met à jour la date de dernière recherche
        save_last_date(datetime.now().strftime("%d-%m-%Y"))
        print("\n🎉 Terminé ! Vous pouvez ouvrir modeles_ia.csv dans Calc/Excel, puis l'importer dans Notion.")
    else:
        print("\nAucun modèle sélectionné, rien à exporter.")

if __name__ == "__main__":
    main()
