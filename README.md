# Arvontakone

Web-pohjainen MVP jääkiekkovuoron tasaväkisten joukkueiden arvontaan.

## Paikallinen ajo

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
uvicorn app.main:app --reload
```

Avaa selaimessa: http://127.0.0.1:8000

## Render-deploy

1. Laita tämä kansio GitHub-repositoryyn.
2. Renderissä: New → Blueprint → valitse repository.
3. Lisää environment variables:
   - `NIMENHUUTO_EMAIL`
   - `NIMENHUUTO_PASSWORD`
4. Deploy.

## Käyttö

- Syötä Nimenhuuto-tapahtuman URL.
- Paina `Hae ilmoittautuneet`.
- Tarkista lista.
- Paina `Arvo joukkueet`.

Jos Nimenhuuto-parsinta ei toimi sivun HTML-rakenteen vuoksi, voit käyttää manuaalista osallistujalistaa käyttöliittymän tekstikentässä.
