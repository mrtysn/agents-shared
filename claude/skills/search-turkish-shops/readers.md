# Readers per shop

Each reader runs in a tab already open on that shop. Each one takes one search page,
fetched with `fetch()`, and returns cards of the form `{name, href, text}` or offers of
the form `{name, href, price, inStock}`. A runner loops over the shortlist with one request
per model, at least 3 seconds apart. It keeps the cheapest in-stock offer whose name
matches the model's regex and none of the accessory words (kılıf, case, yedek, tek kulak,
yenilenmiş, teşhir…), then saves the result to `localStorage`.

Prices in card text: strip installment lines first, then take the lowest `1.234,56 TL` / `₺1.234`
at or above a floor that suits the category (600 TL for earbuds):

```js
const price = t => { const m = [...t.replace(/\d+\s*(?:x|×|ay)\s*[\d.]+(?:,\d+)?\s*(?:TL|₺)/gi, ' ')
  .matchAll(/(\d{1,3}(?:\.\d{3})+|\d{3,6})(?:,\d{1,2})?\s*(?:TL|₺)|₺\s*(\d{1,3}(?:\.\d{3})+|\d{3,6})/g)]
  .map(x => parseInt((x[1] || x[2]).replace(/\./g, ''), 10)).filter(p => p >= 600); return m.length ? Math.min(...m) : null; };
const page = async url => new DOMParser().parseFromString(await (await fetch(url, {credentials: 'include'})).text(), 'text/html');
```

A regex `g` flag keeps `lastIndex` between `test` and `matchAll`; reset it, or build a fresh
regex, before every `matchAll`.

## Teknosa

Search HTML holds the cards. Product links match `-p-\d+`. Climb from each link to the first
ancestor whose text holds a price and is under about 2,500 characters. The link's `title` is the name.

## Vatan Bilgisayar

```js
const cards = d => [...d.querySelectorAll('.product-list--list-page')].map(el => ({
  name: (el.querySelector('.product-list__product-name') || el).textContent.replace(/\s+/g, ' '),
  href: new URL(el.querySelector('a[href]').getAttribute('href'), location.origin).href,
  text: el.textContent.replace(/\s+/g, ' ')}));
// page('/arama/' + encodeURIComponent(q) + '/')
```

## MediaMarkt Türkiye

The search HTML carries the result as JSON. Read it, not the cards:

```js
const h = await (await fetch('/tr/search.html?query=' + encodeURIComponent(q))).text();
const i = h.indexOf('window.__PRELOADED_STATE__ = '), j = h.indexOf('</script>', i);
// the state is a JavaScript literal holding `undefined`, which JSON.parse refuses
const ap = JSON.parse(h.slice(i + 29, j).replace(/;\s*$/, '').replace(/:undefined([,}\]])/g, ':null$1')).apolloState;
for (const k of Object.keys(ap).filter(k => k.startsWith('GraphqlProduct:'))) {
  const p = ap[k], id = p.id;
  const inStock = ap['CofrOnlineStatusFeature:Media:tr:' + id]?.isAvailableAndBuyable;
  const pf = ap['CofrPriceFeature:Media:tr:' + id];
  const amount = Math.min(...[pf?.price?.amount, pf?.promoPrice?.amount].filter(Boolean));
  // p.title, location.origin + p.url
}
```

## Trendyol

The search HTML embeds the result list as `"products":[…]` inside
`window["__single-search-result__PROPS"]`. Cut out the array by bracket depth and parse it.
Each product has `brand`, `name`, `url`, and `price.current`. A `priceLabels` entry that says
"sepette" marks a cart price. The search lists only items in stock.

## D&R

Product links match `urunno=`. Search cards fill in their prices after load, so the fetched HTML
lacks them. Read the live search page, or the product page, for the price. The `kablosuz kulaklık`
search page's brand filter shows which audio brands it stocks.

## Amazon Türkiye

Cards are `[data-component-type="s-search-result"]`: the title is in `h2`, the price in
`.a-price .a-offscreen` and the ASIN in `data-asin`. A card with no price ("Normalden yüksek
fiyat") has its offers at `/dp/<ASIN>?aod=1`, in `#aod-offer`.
