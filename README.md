# Mijn Nachtvlinders — publieksversie 1.0

## Nieuwe opzet

- Eén doorlopende pagina zonder losse tabbladen.
- Een bestaand GeoJSON-gebied wordt bovenaan gekozen; de tekenkaart opent alleen op verzoek.
- Occurrences- en samples-ZIP-bestanden worden op dezelfde pagina geladen.
- Periode en negen analyse-overzichten staan direct zichtbaar.
- Meerdere overzichten kunnen tegelijk worden geselecteerd.
- De analyse start na de keuze; targetsoorten worden automatisch vernieuwd.
- Uitleg en privacy staan onderaan.

Nieuw:
- overzicht **🎯 Target species**;
- zoekt Lepidoptera via de openbare iNaturalist v1 API;
- kandidaten zijn soorten die niet voorkomen in de geüploade ButterflyCount-data binnen het gekozen gebied;
- alleen iNaturalist-waarnemingen buiten het gebied, maar binnen 5 / 10 / 25 / 50 km van de gebiedsgrens;
- standaard 25 km;
- filter op afgelopen 1 / 3 / 5 / 10 jaar;
- optioneel alleen Research Grade;
- minimum aantal nabije waarnemingen;
- per soort: dichtstbijzijnde afstand, aantal nabije waarnemingen en laatste waarneming;
- soorten kunnen als target worden geselecteerd, op kaart bekeken en als CSV gedownload.

## Belangrijk
De targetzoekfunctie haalt maximaal 10.000 iNaturalist-waarnemingen per zoekactie op.
Als iNaturalist meer resultaten meldt, toont de app een waarschuwing en kan de kandidatenlijst onvolledig zijn.

De app houdt ongeveer 1 seconde pauze tussen opeenvolgende iNaturalist API-pagina's.

## GitHub / Streamlit Community Cloud
Vervang:
- `app.py`
- `requirements.txt`

Gebruik Python 3.12.

Bestaande GeoJSON-bestanden en ButterflyCount/eBMS moth-trap exports blijven werken.
