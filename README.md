# Mijn Nachtvlinders — publieksversie 1.4

## Nieuw in 1.4

- De kopfoto wordt in haar volledige oorspronkelijke beeldverhouding getoond, zonder afsnijden.
- De tweede vlinderfoto is beter zichtbaar als rustige pagina-achtergrond.
- Na het kiezen van een gebied blijft alleen het actieve gebied met **Ander gebied kiezen** staan.
- Na het laden van occurrences en samples verdwijnt het uploadvak en verschijnt **Andere bestanden kiezen**.

## Nieuw in 1.3

- De kopfoto is compacter, zodat de bediening sneller in beeld komt.
- Een tweede vlinderfoto is subtiel als achtergrond over de pagina verwerkt.
- De technische regels met namen van geüploade gebieds- en ButterflyCount-bestanden zijn verborgen; de bestanden blijven wel actief.

## Nieuw in 1.2

- De aangeleverde nachtvlinderfoto vormt de brede achtergrond van de kop.
- Een contrastlaag houdt titel en introductie goed leesbaar op mobiel en desktop.
- Modernere typografie, witruimte, knoppen, informatiekaarten en metrics.
- De overzichtskeuzes staan samen in een rustige visuele kaart.
- Upload- en resultaatblokken hebben een consistentere, zachtere vormgeving.

## Nieuw in 1.1

- Het meegeleverde `mijn_nachtvlindergebieden.geojson` wordt bij een nieuwe sessie automatisch geladen.
- Geüploade ZIP-bestanden worden gecachet en niet bij iedere dashboardkeuze opnieuw verwerkt.
- Nieuw overzicht **Beste metingen**, aflopend op aantal soorten, met een gecombineerde grafiek voor soorten en individuen.
- Optioneel kunnen de twee ButterflyCount-ZIP's automatisch worden geladen uit `private_data/`.

> Plaats persoonlijke exports alleen in `private_data/` bij een lokale installatie of een privé-repository. In een publieke GitHub-repository zijn deze bestanden voor anderen zichtbaar.

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
