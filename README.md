# oura_test
Marias oura app

Et personlig prosjekt for å hente og analysere mine egne helse- og aktivitetsdata fra [Oura API v2](https://cloud.ouraring.com/v2/docs).

Krever kun Python 3 (`python3`), ingen ekstra pakker.

## Oppsett

1. Opprett en app på [Oura developer portal](https://cloud.ouraring.com/oauth/applications) med Redirect URI `http://localhost:8080/callback`.
2. Lag en fil `.env` i prosjektmappen:
   ```
   OURA_CLIENT_ID=din client id
   OURA_CLIENT_SECRET=din client secret
   OURA_REDIRECT_URI=http://localhost:8080/callback
   ```
   `OURA_REDIRECT_URI` må være nøyaktig lik Redirect URI i Oura-appen.

## Bruk

| Kommando | Hva den gjør |
|---|---|
| `python3 oura.py` | Logger inn og viser personlig info og søvnscore for de siste 7 dagene |
| `python3 export.py` | Laster ned alle tilgjengelige data til `data/<endepunkt>.json` |
| `python3 export.py 2023-01-01` | Laster ned data fra en gitt dato |
| `python3 analyze_awakenings.py` | Analyserer nattlige oppvåkninger og hva som skjer før dem (krever `data/` fra `export.py`) |

Første gang åpnes nettleseren for innlogging i Oura. Tokens lagres i `tokens.json` og fornyes automatisk, så senere kjøringer trenger ikke nettleseren.

## Personvern

`.env`, `tokens.json` og `data/` inneholder hemmeligheter og helsedata og ligger i `.gitignore`. De skal aldri committes.

## GitHub Pages

Oura krever lenker til personvernerklæring og tjenestevilkår når man registrerer en app. Disse publiseres med GitHub Pages:

- https://mselivanova.github.io/oura_test/
- [Privacy Policy](https://mselivanova.github.io/oura_test/legal/privacy_policy.html) (`legal/privacy_policy.html`)
- [Terms of Service](https://mselivanova.github.io/oura_test/legal/terms_of_service.html) (`legal/terms_of_service.html`)
