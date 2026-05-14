import os
import re
import pandas as pd
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from playwright.sync_api import sync_playwright
import uvicorn

app = FastAPI()

CSV_FILE = "pelaajat.csv"


def lue_pelaajat():
    try:
        df = pd.read_csv(CSV_FILE, sep=";", skiprows=1)
    except Exception:
        df = pd.read_csv(CSV_FILE, sep=";")

    df.columns = df.columns.str.strip()

    if "Rooli" not in df.columns:
        raise ValueError(f"CSV-tiedostosta puuttuu Rooli-sarake. Sarakkeet: {df.columns.tolist()}")

    df["Rooli"] = df["Rooli"].astype(str).str.strip().str.upper()
    return df


def hae_nimenhuuto_ilmoittautuneet(event_url):
    user = os.environ.get("NIMENHUUTO_USER")
    password = os.environ.get("NIMENHUUTO_PASS")

    if not user or not password:
        raise ValueError("NIMENHUUTO_USER tai NIMENHUUTO_PASS puuttuu Renderin Environment Variables -asetuksista.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()

        page.goto(event_url, wait_until="networkidle")

        # Jos ohjautui kirjautumiseen
        if "sessions/new" in page.url or "login" in page.url:
            inputs = page.locator("input").evaluate_all(
                """els => els.map(e => ({
                    type: e.type,
                    name: e.name,
                    id: e.id,
                    placeholder: e.placeholder
                }))"""
            )
            print("LOGIN INPUTS:", inputs)

            page.locator('input[type="email"], input[name*="email"], input[name*="login"], input[type="text"]').first.fill(user)
            page.locator('input[type="password"]').first.fill(password)
            page.locator('button[type="submit"], input[type="submit"]').first.click()

            page.wait_for_load_state("networkidle")
            page.goto(event_url, wait_until="networkidle")

        print("FINAL URL:", page.url)
        title = page.title()
        text = page.inner_text("body")

        print("PAGE TITLE:", title)
        print("PAGE TEXT START:")
        print(text[:5000])
        print("PAGE TEXT END")

        browser.close()

    # Debug: jos ollaan yhä kirjautumissivulla
    if "Kirjaudu jäsensivuille" in text or "Palvelun käyttö edellyttää evästeiden" in text:
        raise ValueError(
            "Nimenhuuto-kirjautuminen ei onnistunut. Tarkista Renderin NIMENHUUTO_USER ja NIMENHUUTO_PASS. "
            "Jos käytät Google-kirjautumista, tarvitsemme erillisen Nimenhuuto-salasanakirjautumisen."
        )

    # Ensimmäinen yritys: etsi rivit IN/Tulossa-osion ympäriltä
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    print("LINES:", lines[:200])

    in_keywords = ["IN", "Tulossa", "Osallistuu"]
    out_keywords = ["OUT", "Ei tulossa", "MAYBE", "Ehkä", "Kommentit", "Comments"]

    start = None
    end = None

    for i, line in enumerate(lines):
        if line in in_keywords:
            start = i + 1
            break

    if start is not None:
        for j in range(start, len(lines)):
            if lines[j] in out_keywords:
                end = j
                break

        candidate_lines = lines[start:end] if end else lines[start:]
    else:
        candidate_lines = []

    nimet = []
    for line in candidate_lines:
        if len(line) < 2:
            continue
        if any(x in line.lower() for x in [
            "ilmoittaudu",
            "kommentti",
            "pelaajaa",
            "osallistujat",
            "muokkaa",
            "poista",
            "takaisin",
            "valikko",
        ]):
            continue
        nimet.append(line)

    unique = []
    for n in nimet:
        if n not in unique:
            unique.append(n)

    if not unique:
        raise ValueError(
            "Ilmoittautuneita ei löytynyt Nimenhuuto-sivulta. "
            "Katso Renderin logeista kohdat PAGE TEXT START ja LINES ja lähetä ne tänne."
        )

    return unique

def normalisoi_nimi(n):
    return str(n).strip().lower()


def numero(rivi, sarake):
    value = pd.to_numeric(rivi.get(sarake, 0), errors="coerce")
    if pd.isna(value):
        return 0
    return float(value)


def laske_arvo(r):
    rooli = str(r["Rooli"]).strip().upper()

    if rooli == "G":
        return 0.6 * numero(r, "Torjuntataito") + 0.4 * numero(r, "Liike")

    return (
        0.25 * numero(r, "Kiekollinen taito")
        + 0.20 * numero(r, "Luistelutaito")
        + 0.20 * numero(r, "Kamppailutaito")
        + 0.15 * numero(r, "Laukauksen laatu")
        + 0.20 * numero(r, "Joukkuepelaaminen")
    )


def rooli_nimi(rooli):
    rooli = str(rooli).strip().upper()
    return {"O": "Hyökkääjä", "D": "Puolustaja", "G": "Maalivahti"}.get(rooli, rooli)


def arvioi(j1, j2):
    score = 10 * abs(j1["arvo"].sum() - j2["arvo"].sum())

    for rooli in ["O", "D"]:
        score += 5 * abs((j1["Rooli"] == rooli).sum() - (j2["Rooli"] == rooli).sum())

    for sarake in ["Kiekollinen taito", "Luistelutaito", "Kamppailutaito", "Laukauksen laatu", "Joukkuepelaaminen"]:
        if sarake in j1.columns:
            score += 2 * abs(
                pd.to_numeric(j1[sarake], errors="coerce").fillna(0).sum()
                - pd.to_numeric(j2[sarake], errors="coerce").fillna(0).sum()
            )

    return score


def jaa_kenttapelaajat(kentta, iterations=20000):
    best = None
    best_score = float("inf")

    for _ in range(iterations):
        shuffled = kentta.sample(frac=1).reset_index(drop=True)
        mid = len(shuffled) // 2

        j1 = shuffled.iloc[:mid].copy()
        j2 = shuffled.iloc[mid:].copy()

        score = arvioi(j1, j2)

        if score < best_score:
            best_score = score
            best = (j1, j2)

    return best, best_score


def jaa_maalivahdit(mv):
    if len(mv) < 2:
        raise ValueError("Arvonta vaatii vähintään kaksi ilmoittautunutta maalivahtia.")

    mv = mv.sample(frac=1).reset_index(drop=True)
    return mv.iloc[[0]].copy(), mv.iloc[[1]].copy()


def arvo_joukkueet(event_url):
    ilmoittautuneet = hae_nimenhuuto_ilmoittautuneet(event_url)

    df = lue_pelaajat()

    if "Nimi" not in df.columns:
        raise ValueError("CSV-tiedostosta puuttuu Nimi-sarake.")

    df["_nimi_norm"] = df["Nimi"].apply(normalisoi_nimi)
    ilmo_norm = [normalisoi_nimi(n) for n in ilmoittautuneet]

    mukana = df[df["_nimi_norm"].isin(ilmo_norm)].copy()

    loytyneet_norm = set(mukana["_nimi_norm"].tolist())
    puuttuvat = [n for n in ilmoittautuneet if normalisoi_nimi(n) not in loytyneet_norm]

    if len(mukana) < 4:
        raise ValueError(f"Liian vähän CSV:stä löytyneitä ilmoittautuneita. Löytyi {len(mukana)}. Puuttuvat: {puuttuvat}")

    mukana["arvo"] = mukana.apply(laske_arvo, axis=1)

    mv = mukana[mukana["Rooli"] == "G"].copy()
    kentta = mukana[mukana["Rooli"] != "G"].copy()

    j1_mv, j2_mv = jaa_maalivahdit(mv)
    (j1_k, j2_k), score = jaa_kenttapelaajat(kentta)

    j1 = pd.concat([j1_mv, j1_k]).reset_index(drop=True)
    j2 = pd.concat([j2_mv, j2_k]).reset_index(drop=True)

    return j1, j2, score, ilmoittautuneet, puuttuvat


def joukkue_html(title, team):
    rows = ""

    for _, r in team.iterrows():
        rows += f"""
        <tr>
            <td>{r.get("Nimi", "")}</td>
            <td>{rooli_nimi(r["Rooli"])}</td>
            <td>{r["arvo"]:.2f}</td>
        </tr>
        """

    return f"""
    <div class="card">
        <h2>{title}</h2>
        <div class="total">Kokonaisarvo: {team["arvo"].sum():.2f}</div>
        <table>
            <tr><th>Nimi</th><th>Rooli</th><th>Arvo</th></tr>
            {rows}
        </table>
    </div>
    """


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
        <meta charset="utf-8">
        <title>Arvontakone</title>
        <style>
            body { font-family: Arial; background:#0f172a; color:#e5e7eb; padding:40px; }
            .container { max-width:900px; margin:auto; }
            input { width:100%; padding:14px; border-radius:10px; border:0; font-size:16px; }
            button { margin-top:18px; padding:14px 24px; border:0; border-radius:10px; background:#38bdf8; font-weight:bold; cursor:pointer; }
            .card { background:#1e293b; padding:24px; border-radius:18px; margin-top:20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🏒 Arvontakone</h1>
            <div class="card">
                <form method="post" action="/arvo">
                    <label>Nimenhuuto-tapahtuman URL</label><br><br>
                    <input name="event_url" placeholder="https://claybay.nimenhuuto.com/events/20044352" required>
                    <button type="submit">Hae ilmoittautuneet ja arvo joukkueet</button>
                </form>
            </div>
        </div>
    </body>
    </html>
    """


@app.post("/arvo", response_class=HTMLResponse)
def arvo(event_url: str = Form(...)):
    try:
        j1, j2, score, ilmoittautuneet, puuttuvat = arvo_joukkueet(event_url)

        puuttuvat_html = ""
        if puuttuvat:
            puuttuvat_html = "<h3>CSV:stä puuttuvat ilmoittautuneet</h3><ul>" + "".join(f"<li>{n}</li>" for n in puuttuvat) + "</ul>"

        return f"""
        <html>
        <head>
            <meta charset="utf-8">
            <title>Joukkuejako</title>
            <style>
                body {{ font-family: Arial; background:#0f172a; color:#e5e7eb; padding:40px; }}
                .container {{ max-width:1200px; margin:auto; }}
                .teams {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
                .card {{ background:#1e293b; padding:24px; border-radius:18px; }}
                table {{ width:100%; border-collapse:collapse; }}
                th, td {{ padding:10px; border-bottom:1px solid #334155; text-align:left; }}
                th {{ color:#bfdbfe; }}
                .total {{ color:#93c5fd; font-weight:bold; margin-bottom:12px; }}
                a {{ color:#38bdf8; }}
                .note {{ margin-top:20px; color:#a7f3d0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🏒 Joukkuejako</h1>
                <p><a href="/">← Takaisin</a></p>

                <div class="teams">
                    {joukkue_html("Joukkue 1", j1)}
                    {joukkue_html("Joukkue 2", j2)}
                </div>

                <div class="note">Tasapainopisteet: {score:.2f}</div>
                <div class="note">Nimenhuudosta löytyi {len(ilmoittautuneet)} ilmoittautunutta.</div>
                {puuttuvat_html}
            </div>
        </body>
        </html>
        """

    except Exception as e:
        return f"""
        <html>
        <body style="font-family:Arial; background:#0f172a; color:#e5e7eb; padding:40px;">
            <h1>Virhe</h1>
            <div style="background:#7f1d1d; color:#fee2e2; padding:20px; border-radius:10px;">
                {str(e)}
            </div>
            <p><a style="color:#38bdf8;" href="/">Takaisin</a></p>
        </body>
        </html>
        """


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
