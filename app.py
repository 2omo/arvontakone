import os
import random
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI()

CSV_FILE = "pelaajat.csv"


def lue_pelaajat():
    try:
        df = pd.read_csv(CSV_FILE, sep=";", skiprows=1)
    except Exception:
        df = pd.read_csv(CSV_FILE, sep=";")

    df.columns = df.columns.str.strip()

    print("SARAKKEET:", df.columns.tolist())

    if "Rooli" not in df.columns:
        raise ValueError(f"CSV-tiedostosta puuttuu Rooli-sarake. Sarakkeet: {df.columns.tolist()}")

    df["Rooli"] = df["Rooli"].astype(str).str.strip().str.upper()

    return df


def numero(rivi, sarake):
    if sarake not in rivi:
        return 0
    value = pd.to_numeric(rivi.get(sarake, 0), errors="coerce")
    if pd.isna(value):
        return 0
    return float(value)


def laske_arvo(r):
    rooli = str(r["Rooli"]).strip().upper()

    if rooli == "G":
        return (
            0.6 * numero(r, "Torjuntataito")
            + 0.4 * numero(r, "Liike")
        )

    return (
        0.25 * numero(r, "Kiekollinen taito")
        + 0.20 * numero(r, "Luistelutaito")
        + 0.20 * numero(r, "Kamppailutaito")
        + 0.15 * numero(r, "Laukauksen laatu")
        + 0.20 * numero(r, "Joukkuepelaaminen")
    )


def rooli_nimi(rooli):
    rooli = str(rooli).strip().upper()
    if rooli == "O":
        return "Hyökkääjä"
    if rooli == "D":
        return "Puolustaja"
    if rooli == "G":
        return "Maalivahti"
    return rooli


def arvioi(j1, j2):
    score = 0

    # Kokonaisarvon ero
    score += 10 * abs(j1["arvo"].sum() - j2["arvo"].sum())

    # Roolitasapaino
    for rooli in ["O", "D"]:
        score += 5 * abs((j1["Rooli"] == rooli).sum() - (j2["Rooli"] == rooli).sum())

    # Taitokohtainen tasapaino
    sarakkeet = [
        "Kiekollinen taito",
        "Luistelutaito",
        "Kamppailutaito",
        "Laukauksen laatu",
        "Joukkuepelaaminen",
    ]

    for sarake in sarakkeet:
        if sarake in j1.columns and sarake in j2.columns:
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
        raise ValueError("Arvonta vaatii vähintään kaksi maalivahtia, koska maalivahdit jaetaan eri joukkueisiin.")

    mv = mv.sample(frac=1).reset_index(drop=True)

    j1_mv = mv.iloc[[0]].copy()
    j2_mv = mv.iloc[[1]].copy()

    return j1_mv, j2_mv


def arvo_joukkueet():
    df = lue_pelaajat()
    df["arvo"] = df.apply(laske_arvo, axis=1)

    mv = df[df["Rooli"] == "G"].copy()
    kentta = df[df["Rooli"] != "G"].copy()

    j1_mv, j2_mv = jaa_maalivahdit(mv)
    (j1_k, j2_k), score = jaa_kenttapelaajat(kentta)

    j1 = pd.concat([j1_mv, j1_k]).reset_index(drop=True)
    j2 = pd.concat([j2_mv, j2_k]).reset_index(drop=True)

    return j1, j2, score


def joukkue_html(title, team):
    rows = ""

    for _, r in team.iterrows():
        nimi = r.get("Nimi", r.iloc[0])
        rooli = rooli_nimi(r["Rooli"])
        arvo = round(r["arvo"], 2)

        rows += f"""
        <tr>
            <td>{nimi}</td>
            <td>{rooli}</td>
            <td>{arvo}</td>
        </tr>
        """

    return f"""
    <div class="card">
        <h2>{title}</h2>
        <div class="total">Kokonaisarvo: {team["arvo"].sum():.2f}</div>
        <table>
            <thead>
                <tr>
                    <th>Nimi</th>
                    <th>Rooli</th>
                    <th>Arvo</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!doctype html>
    <html lang="fi">
    <head>
        <meta charset="utf-8">
        <title>Arvontakone</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background: #0f172a;
                color: #e5e7eb;
                margin: 0;
                padding: 40px;
            }
            .container {
                max-width: 1100px;
                margin: auto;
            }
            h1 {
                font-size: 42px;
                margin-bottom: 10px;
            }
            p {
                color: #cbd5e1;
            }
            button {
                background: #38bdf8;
                color: #020617;
                border: none;
                padding: 14px 24px;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
                cursor: pointer;
                margin: 20px 0;
            }
            button:hover {
                background: #7dd3fc;
            }
            .teams {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 24px;
                margin-top: 24px;
            }
            .card {
                background: #1e293b;
                border-radius: 18px;
                padding: 24px;
                box-shadow: 0 12px 30px rgba(0,0,0,0.35);
            }
            .total {
                margin-bottom: 16px;
                color: #93c5fd;
                font-weight: bold;
            }
            table {
                width: 100%;
                border-collapse: collapse;
            }
            th, td {
                padding: 10px;
                border-bottom: 1px solid #334155;
                text-align: left;
            }
            th {
                color: #bfdbfe;
            }
            .score {
                margin-top: 20px;
                color: #a7f3d0;
                font-weight: bold;
            }
            .error {
                background: #7f1d1d;
                color: #fee2e2;
                padding: 16px;
                border-radius: 10px;
                margin-top: 20px;
            }
            @media (max-width: 800px) {
                .teams {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🏒 Arvontakone</h1>
            <p>Arpoo kaksi tasaväkistä joukkuetta pelaajataulukon perusteella.</p>

            <form method="post" action="/arvo">
                <button type="submit">Arvo joukkueet</button>
            </form>
        </div>
    </body>
    </html>
    """


@app.post("/arvo", response_class=HTMLResponse)
def arvo():
    try:
        j1, j2, score = arvo_joukkueet()

        return f"""
        <!doctype html>
        <html lang="fi">
        <head>
            <meta charset="utf-8">
            <title>Arvontakone</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background: #0f172a;
                    color: #e5e7eb;
                    margin: 0;
                    padding: 40px;
                }}
                .container {{
                    max-width: 1200px;
                    margin: auto;
                }}
                a {{
                    color: #38bdf8;
                    text-decoration: none;
                    font-weight: bold;
                }}
                .teams {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 24px;
                    margin-top: 24px;
                }}
                .card {{
                    background: #1e293b;
                    border-radius: 18px;
                    padding: 24px;
                    box-shadow: 0 12px 30px rgba(0,0,0,0.35);
                }}
                .total {{
                    margin-bottom: 16px;
                    color: #93c5fd;
                    font-weight: bold;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                }}
                th, td {{
                    padding: 10px;
                    border-bottom: 1px solid #334155;
                    text-align: left;
                }}
                th {{
                    color: #bfdbfe;
                }}
                .score {{
                    margin-top: 20px;
                    color: #a7f3d0;
                    font-weight: bold;
                }}
                @media (max-width: 800px) {{
                    .teams {{
                        grid-template-columns: 1fr;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🏒 Joukkuejako</h1>
                <a href="/">← Arvo uudestaan</a>

                <div class="teams">
                    {joukkue_html("Joukkue 1", j1)}
                    {joukkue_html("Joukkue 2", j2)}
                </div>

                <div class="score">Tasapainopisteet: {score:.2f}</div>
            </div>
        </body>
        </html>
        """

    except Exception as e:
        return f"""
        <!doctype html>
        <html lang="fi">
        <head>
            <meta charset="utf-8">
            <title>Virhe</title>
        </head>
        <body style="font-family: Arial; background:#0f172a; color:#e5e7eb; padding:40px;">
            <h1>Virhe arvonnassa</h1>
            <div style="background:#7f1d1d; color:#fee2e2; padding:16px; border-radius:10px;">
                {str(e)}
            </div>
            <p><a style="color:#38bdf8;" href="/">Takaisin</a></p>
        </body>
        </html>
        """


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
