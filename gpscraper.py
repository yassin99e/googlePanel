import csv
import time
import random
import urllib.parse
import os
import traceback
import pandas as pd
import argparse
import logging
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

# ---------------------------------------------------------
# Configuration du Logging
# ---------------------------------------------------------
# Sur Ubuntu Server, nous écrivons dans un fichier et dans la console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("scraper_debug.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# Fonction de similarité
# ---------------------------------------------------------
def is_similar(a, b, threshold=0.55):
    if not a or not b or str(a) == 'nan' or str(b) == 'nan':
        return False
    ratio = SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()
    return ratio >= threshold

# ---------------------------------------------------------
# Configuration du Navigateur Anti-Bot
# ---------------------------------------------------------
def setup_driver(headless=True):
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
    
    # Randomisation légère de la taille d'écran pour paraître humain
    width = random.randint(1024, 1920)
    height = random.randint(768, 1080)
    options.add_argument(f"--window-size={width},{height}")
    options.add_argument("--lang=fr-FR")
    
    # User-Agents variés (peuvent être enrichis)
    user_agents = [
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ]
    options.add_argument(f"user-agent={random.choice(user_agents)}")

    try:
        driver = uc.Chrome(options=options, headless=headless, version_main=119)
        driver.implicitly_wait(5)
        return driver
    except Exception as e:
        logger.error(f"Erreur lors du lancement du navigateur : {e}")
        raise

# ---------------------------------------------------------
# Logique d'extraction
# ---------------------------------------------------------
# ---------------------------------------------------------
# Logique d'extraction (Version Debug & Cookies)
# ---------------------------------------------------------
def scrape_google_data(driver, nom, ville):
    query = urllib.parse.quote(f"{nom} {ville} Maroc")
    url_search = f"https://www.google.com/search?q={query}&hl=fr"
    
    try:
        driver.get(url_search)
        # Jitter initial : on attend que la page "respire"
        time.sleep(random.uniform(3.5, 6.0))
        
        # Détection de Captcha ou blocage
        if "sorry/index" in driver.current_url or "recaptcha" in driver.page_source.lower():
            return "BLOCKED"
            
        # NOUVEAU : Acceptation des cookies avec probabilité (comme un humain)
        if random.random() > 0.1: # 90% de chances de cliquer
            try:
                boutons = driver.find_elements(By.XPATH, "//button[.//div[contains(text(), 'Tout accepter') or contains(text(), 'Accept all')]]")
                if boutons:
                    boutons[0].click()
                    time.sleep(random.uniform(1.0, 2.5)) 
            except:
                pass 
            
    except Exception as e:
        logger.error(f"  -> Erreur de chargement : {e}")
        return None

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    data = {
        "Nom de recherche": nom,
        "Ville": ville,
        "Nom trouvé": "",
        "Secteur d'activité": "",
        "Adresse": "",
        "Téléphone": "",
        "Site Web": "",
        "Source Site Web": "Aucun"
    }
    
    # 1. Recherche dans la fiche Google (Knowledge Panel)
    rhs_panel = soup.find(id="rhs")
    
    if rhs_panel:
        title_node = rhs_panel.find(attrs={"data-attrid": "title"})
        if title_node: data["Nom trouvé"] = title_node.text.strip()
        
        subtitle_node = rhs_panel.find(attrs={"data-attrid": "subtitle"})
        if subtitle_node: data["Secteur d'activité"] = subtitle_node.text.strip()
        
        addr_node = rhs_panel.find(attrs={"data-attrid": "kc:/location/location:address"})
        if addr_node:
            val = addr_node.find(class_="LrzXr")
            if val: data["Adresse"] = val.text.strip()
            
        phone_node = rhs_panel.find(attrs={"data-attrid": "kc:/local:alt phone"})
        if phone_node:
            val = phone_node.find("span", class_="LrzXr") or phone_node.find("span", attrs={"aria-label": True})
            if val: data["Téléphone"] = val.text.strip()
            
        for a_tag in rhs_panel.find_all('a', href=True):
            text_link = a_tag.get_text(strip=True).lower()
            if "site web" in text_link or "website" in text_link:
                data["Site Web"] = a_tag['href']
                data["Source Site Web"] = "Fiche Google"
                break

    # 2. Fallback : 1er lien organique
    if not data["Site Web"]:
        first_result = None
        g_divs = soup.find_all('div', class_='g')
        for div in g_divs:
            a_tag = div.find('a', href=True)
            if a_tag and str(a_tag['href']).startswith('http'):
                first_result = a_tag
                break

        if first_result:
            url = first_result.get('href', '')
            title_node = first_result.find('h3')
            title_text = title_node.text if title_node else ""
            
            domain = urllib.parse.urlparse(url).netloc.replace("www.", "")
            domain_name = domain.split('.')[0] 
            
            # NOUVEAU : Affichage de ce que le script voit réellement
            logger.debug(f"    [Détails] 1er lien : {domain_name} | {title_text}")
            
            # Similarité à 0.45
            if is_similar(nom, title_text, 0.45) or is_similar(nom, domain_name, 0.45):
                exclude_list = ['linkedin', 'facebook', 'instagram', 'telecontact', 'kerix', 'pagesjaunes', 'marocannuaire', 'kompass']
                if not any(ex in domain.lower() for ex in exclude_list):
                    data["Site Web"] = url
                    data["Source Site Web"] = "1er lien similaire"
            else:
                logger.debug("    [Détails] Lien rejeté : ressemblance insuffisante.")
                    
    return data

# ---------------------------------------------------------
# Exécution Principale
# ---------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Google Maps Scraper for AWS EC2 (Ubuntu Server)")
    parser.add_argument("--input", "-i", type=str, required=True, help="Fichier CSV d'entrée (ex: part1.csv)")
    parser.add_argument("--output", "-o", type=str, required=True, help="Fichier CSV de sortie (ex: output_part1.csv)")
    parser.add_argument("--gui", action="store_true", help="Activer l'interface (Désactivé par défaut sur Serveur)")
    args = parser.parse_args()

    logger.info(f"🚀 Lancement (Entrée: {args.input} | Sortie: {args.output})")
    
    try:
        driver = setup_driver(headless=not args.gui)
    except Exception as e:
        logger.error(f"Fermeture prématurée : {e}")
        return

    fieldnames = ["Nom de recherche", "Ville", "Nom trouvé", "Secteur d'activité", "Adresse", "Téléphone", "Site Web", "Source Site Web"]
    
    # Chargement du fichier CSV d'entrée
    try:
        df = pd.read_csv(args.input, sep=None, engine='python', encoding='utf-8-sig')
        df.columns = df.columns.str.strip().str.lower()
    except Exception as e:
        logger.error(f"Impossible de lire {args.input} : {e}")
        driver.quit()
        return

    if 'nom' not in df.columns or 'ville' not in df.columns:
        logger.error("❌ ERREUR : Colonnes 'nom' et 'ville' introuvables.")
        driver.quit()
        return

    # Gestion de la reprise automatique (Basée sur le couple Nom + Ville)
    lignes_deja_traitees = set()
    if os.path.exists(args.output):
        try:
            with open(args.output, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    n = str(row.get("Nom de recherche", "")).strip()
                    v = str(row.get("Ville", "")).strip()
                    lignes_deja_traitees.add(f"{n}|{v}")
            logger.info(f"🔄 Reprise activée : {len(lignes_deja_traitees)} entreprises déjà traitées dans '{args.output}'.")
        except Exception as e:
            logger.warning(f"Impossible de lire le fichier de reprise : {e}")
            pass
    else:
        with open(args.output, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

    # Configuration des seuils
    RESTART_EVERY = 30  # Redémarrer Chrome toutes les 30 requêtes pour éviter d'être pisté
    counter = 0

    try:
        total = len(df)
        for index, row in df.iterrows():
            nom = str(row.get('nom', '')).strip()
            ville = str(row.get('ville', '')).strip()
            
            cle_unique = f"{nom}|{ville}"
            
            if not nom or nom.lower() == 'nan' or cle_unique in lignes_deja_traitees:
                continue
                
            # Gestion de la rotation de session
            if counter >= RESTART_EVERY:
                logger.info("🔄 Rotation de session : Redémarrage du navigateur...")
                driver.quit()
                time.sleep(random.randint(15, 30))
                driver = setup_driver(headless=not args.gui)
                counter = 0

            logger.info(f"[{index + 1}/{total}] Scraping : {nom} ({ville})")
            
            # Logique de retry sophistiquée
            max_retries = 3
            result = None
            
            for attempt in range(max_retries):
                result = scrape_google_data(driver, nom, ville)
                
                if result == "BLOCKED":
                    # Si bloqué, on fait une grosse pause et on re-essaie
                    wait_sec = random.randint(300, 600) * (attempt + 1)
                    logger.warning(f"🚨 Bloqué (Tentative {attempt+1}/{max_retries}). Pause de {wait_sec//60} min...")
                    time.sleep(wait_sec)
                    # On change d'identité si possible lors du retry (ici reboot browser)
                    driver.quit()
                    driver = setup_driver(headless=not args.gui)
                    continue 
                elif result is None:
                    # Erreur technique, petit wait
                    time.sleep(10)
                    continue
                else:
                    # Succès
                    break
            
            if result and result != "BLOCKED":
                with open(args.output, mode='a', encoding='utf-8-sig', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writerow(result)
                counter += 1
            elif result == "BLOCKED":
                logger.error(f"❌ Échec définitif pour {nom} suite à un blocage multiple.")
            
            # Jitter entre chaque entreprise
            # On simule un temps de lecture/analyse humaine
            time.sleep(random.uniform(5, 12))
            
            # De temps en temps, on fait une pause "café" plus longue
            if counter > 0 and counter % 10 == 0:
                coffee_break = random.randint(60, 180)
                logger.info(f"☕ Pause café de {coffee_break}s...")
                time.sleep(coffee_break)
                    
    except KeyboardInterrupt:
        logger.info("\n⏹ Arrêt manuel par l'utilisateur.")
    except Exception as e:
        logger.error(f"\n❌ Erreur critique : {e}")
        traceback.print_exc()
    finally:
        logger.info("Fermeture du navigateur...")
        try:
            driver.quit()
        except:
            pass
        logger.info(f"Terminé. Résultats dans '{args.output}'.")

if __name__ == "__main__":
    main()