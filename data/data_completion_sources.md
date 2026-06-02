# Data Completion Sources

Last updated: 2026-06-02

## Toyota outlets

- Source: Toyota Malaysia Find a Dealer locator
- URL: https://www.toyota.com.my/en/contact-us/find-a-dealer.html
- Used for Toyota service and body & paint outlet names, outlet codes, addresses, postcodes, coordinates, and service-specific phone numbers where Toyota publishes them.
- Toyota's current locator payload does not publish direct outlet emails, so email fields remain blank rather than inferred.

## Customer postcodes

- Source: OpenStreetMap Nominatim reverse geocoding
- URL: https://nominatim.openstreetmap.org/
- Used to fill postcodes for existing customer-density rows from their existing latitude/longitude values where the reverse-geocode response contained a postcode.

- Source: Malaysia Postcode
- URL: https://postcode.my/
- Used to fill remaining town-level customer postcodes by matching the customer row's city/town name. For aggregated rows such as `Sibu / Selangau`, the first named town was treated as the primary postcode location.

- Additional postcode confirmation sources:
  - Pensiangan / Sepulot, Sabah: https://postcode.my/89950/
  - Pulau Banggi, Sabah: https://postcode.my/89050/
  - Sri Gading, Johor: https://postcode.my/83300/
  - Pakan, Sarawak: https://talikhidmat.sarawak.gov.my/talikhidmat/web/home/agency_view/26

## Traffic police stations

- Source: OpenStreetMap Overpass API
- URL: https://overpass-api.de/
- Used for traffic-police station names, coordinates, and address/phone/postcode tags where present.

- Additional public listing sources used for missing-state traffic-office coordinates:
  - Cawangan Trafik IPD Seremban: https://malaysia.worldplaces.me/ms/city/seremban/view-place/1763839-ipd-seremban-cawangan-trafik.html
  - Pejabat Trafik IPD Ipoh: https://malaysia.worldplaces.me/city/ipoh/view-place/2497419-pejabat-trafik-ipd-ipoh-ipoh-balai-polis.html
  - Balai Polis Trafik Putrajaya: https://malaysia.worldplaces.me/ms/city/putrajaya/view-place/2875919-balai-polis-trafik-putrajaya.html

## Remaining limitations

- Customer-density `weight` values appear to be business/customer counts, not public population counts. Public sources cannot validate or create missing customer weights for states not present in `customers.csv`.
- Toyota outlet emails are not published in the current official Toyota locator payload.
- Some Toyota outlet codes and body & paint phone numbers are blank because the official locator does not publish those fields for those outlet entries.
- Traffic station emails are blank and most traffic phone/address/postcode fields are blank because the public map/listing sources do not publish complete contact records for every station.
