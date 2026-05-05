import pandas as pd
import random
import numpy as np

# --- LUE DATA ---
df = pd.read_csv("pelaajat.csv")

# --- NORMALISOI SARAKKEET ---
df.columns = df.columns.str.strip()

# --- LASKE ARVO ---
def laske_arvo(r):
    if r["Rooli"].lower() == "maalivahti":
        return 0.6 * r.get("Torjuntataito", 0) + 0.4 * r.get("Liike", 0)
    else:
        return (
            0.25 * r.get("Kiekollinen taito", 0)
            + 0.20 * r.get("Luistelutaito", 0)
            + 0.20 * r.get("Kamppailutaito", 0)
            + 0.15 * r.get("Laukaus", 0)
            + 0.20 * r.get("Joukkuepelaaminen", 0)
        )

df["arvo"] = df.apply(laske_arvo, axis=1)

# --- JAETAAN ROOLEITTAIN ---
mv = df[df["Rooli"].str.lower() == "maalivahti"]
kentta = df[df["Rooli"].str.lower() != "maalivahti"]

# --- OPTIMOINTI ---
def arvioi(j1, j2):
    def summa(j):
        return j["arvo"].sum()

    def roolit(j):
        return j["Rooli"].value_counts()

    score = 0

    # kokonaisarvo
    score += 10 * abs(summa(j1) - summa(j2))

    # roolit
    r1, r2 = roolit(j1), roolit(j2)
    for r in ["hyökkääjä", "pakki"]:
        score += 4 * abs(r1.get(r, 0) - r2.get(r, 0))

    return score


def jaa_joukkueet(df, iterations=10000):
    best = None
    best_score = float("inf")

    for _ in range(iterations):
        shuffled = df.sample(frac=1)

        mid = len(shuffled) // 2
        j1 = shuffled.iloc[:mid]
        j2 = shuffled.iloc[mid:]

        score = arvioi(j1, j2)

        if score < best_score:
            best_score = score
            best = (j1, j2)

    return best, best_score


# --- MAALIVAHTIEN JAKO ---
def jaa_mv(mv_df):
    mv_list = mv_df.sample(frac=1).reset_index(drop=True)

    j1 = mv_list.iloc[: len(mv_list)//2]
    j2 = mv_list.iloc[len(mv_list)//2 :]

    return j1, j2


# --- SUORITUS ---
j1_mv, j2_mv = jaa_mv(mv)
(j1_k, j2_k), score = jaa_joukkueet(kentta)

j1 = pd.concat([j1_mv, j1_k])
j2 = pd.concat([j2_mv, j2_k])

# --- TULOSTUS ---
print("\nJOUKKUE 1")
print(j1[["Nimi", "Rooli", "arvo"]])
print("Yhteensä:", j1["arvo"].sum())

print("\nJOUKKUE 2")
print(j2[["Nimi", "Rooli", "arvo"]])
print("Yhteensä:", j2["arvo"].sum())

print("\nTasapainopisteet:", score)