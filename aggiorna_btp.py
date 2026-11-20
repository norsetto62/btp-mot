import json
import re
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.borsaitaliana.it/borsa/obbligazioni/mot/btp/lista.html?page={}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.borsaitaliana.it/borsa/obbligazioni/mot/btp/lista.html",
}


def estrai_titoli_pagina(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    table = soup.find("table")
    if not table:
        return []

    records = []
    for row in table.find_all("tr")[1:]:
        cols = row.find_all(["td", "th"])
        if len(cols) < 2:
            continue

        raw_text = " ".join(cols[0].get_text(" ", strip=True).split())
        desc = " ".join(cols[1].get_text(" ", strip=True).split())

        isin_match = re.search(r"(IT[0-9A-Z]{10})", raw_text)
        if not isin_match:
            continue
        isin = isin_match.group(1)

        # Prezzo ultimo contratto
        ultimo_match = re.search(r"Ultimo:\s*([\d.,]+)", raw_text)
        if not ultimo_match:
            continue
        price_str = ultimo_match.group(1).replace(".", "").replace(",", ".")
        try:
            price = float(price_str)
        except ValueError:
            continue

        # Cedola periodica -> annua (x2 semestrale, x4 trimestrale per BTP Valore / Più)
        cedola_match = re.search(r"Cedola:\s*([\d.,]+)", raw_text)
        cedola_periodica = (
            float(cedola_match.group(1).replace(",", ".")) if cedola_match else 0.0
        )
        moltiplicatore = 4 if ("Valore" in desc or "Piu" in desc) else 2
        coupon = round(cedola_periodica * moltiplicatore, 4)

        # Fallback dal nome del titolo se il campo Cedola è vuoto
        if coupon == 0.0:
            pct_match = re.search(r"(\d+[.,]\d+)\s*%", desc)
            if pct_match:
                coupon = float(pct_match.group(1).replace(",", "."))

        scad_match = re.search(r"Scadenza:\s*(\d{2}/\d{2}/\d{4})", raw_text)
        maturity = scad_match.group(1) if scad_match else ""

        records.append({
            "isin": isin,
            "name": desc,
            "price": price,
            "coupon": coupon,
            "maturity": maturity,
        })

    return records


def main():
    session = requests.Session()
    session.headers.update(HEADERS)

    tutti_i_btp = {}
    page = 1

    print("Avvio scaricamento listino BTP da Borsa Italiana (MOT)...")

    while page <= 20:
        url = BASE_URL.format(page)
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"Stop alla pagina {page}: HTTP {resp.status_code}")
            break

        titoli_pagina = estrai_titoli_pagina(resp.text)
        if not titoli_pagina:
            print(f"Nessun altro titolo valido alla pagina {page}.")
            break

        nuovi = 0
        for item in titoli_pagina:
            if item["isin"] not in tutti_i_btp:
                tutti_i_btp[item["isin"]] = item
                nuovi += 1

        print(f"Pagina {page}: trovati {len(titoli_pagina)} quotati ({nuovi} nuovi)")
        if nuovi == 0:
            break

        page += 1
        time.sleep(0.8)  # Pausa cortese per non attivare rate-limit

    lista_finale = list(tutti_i_btp.values())
    if not lista_finale:
        print("Nessun dato estratto. Verifica la connessione o gli header.")
        return

    # 1. Salva JSON (per import manuale)
    with open("btp_mot_borsa_italiana.json", "w", encoding="utf-8") as f:
        json.dump(lista_finale, f, ensure_ascii=False, indent=2)

    # 2. Salva JS (caricamento automatico nella dashboard locale senza CORS)
    with open("btp_data.js", "w", encoding="utf-8") as f:
        f.write("window.BTP_EXTERNAL_DATA = ")
        json.dump(lista_finale, f, ensure_ascii=False)
        f.write(";\n")

    # 3. Salva CSV pulito
    pd.DataFrame(lista_finale).to_csv("btp_puliti.csv", index=False, encoding="utf-8-sig")

    print(f"\n[OK] Salvati {len(lista_finale)} BTP quotati in:")
    print(" - btp_data.js (caricamento automatico in index.html)")
    print(" - btp_mot_borsa_italiana.json")
    print(" - btp_puliti.csv")


if __name__ == "__main__":
    main()