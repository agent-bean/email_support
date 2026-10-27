# Company website verification

Checked on 2026-10-27. Addresses below are used to construct synthetic emails; they do not verify the sender or provide snapshots for factual evaluation. Original addresses are preserved in `customer-examples-v1`.

| Company | Selected website and identity evidence | Check and decision |
| --- | --- | --- |
| FPT Software | [Official FPT Software home](https://fptsoftware.com/) and [About Us](https://fptsoftware.com/en/about-us) | Existing `https://fptsoftware.com` retained. The official company page identifies FPT Software. |
| Vinamilk | [Vinamilk's 2024 annual report](https://www.vinamilk.com.vn/bao-cao-thuong-nien/bao-cao/2024/doc/en/vinamilk-ar-eng-full-layout-interactive.pdf) and [Vinamilk Shop terms](https://i04-eshop-vn.apps.vinamilk.tech/en/support/terms-of-use) | Existing `https://www.vinamilk.com.vn` retained. The homepage returned HTTP 403 to the automated check; that access restriction does not establish a changed domain. The annual report is historical identity evidence, not a current company profile. |
| Samsung Electronics Vietnam | [Samsung Vietnam newsroom overview](https://news.samsung.com/vn/overview) | Existing `https://www.samsung.com/vn` retained; Samsung's overview lists it as an official website. It is a regional Samsung site, not a standalone legal-entity homepage. |
| Shopee Vietnam | [Shopee Vietnam help center](https://help.shopee.vn/portal/4/article/79422) | Existing `https://shopee.vn` retained; Shopee identifies it as its Vietnam marketplace. |
| Viettel Solutions | [Viettel Solutions official site](https://solutions.viettel.vn/en) and [Vietnam digital technology agency listing](https://ai.dda.gov.vn/chi-tiet-he-thong-tri-tue-nhan-tao/VN-01-0000007-TRA-008-X) | Use `https://solutions.viettel.vn/en`. The original `https://viettelsolutions.vn` failed TLS certificate validation during the check; this alone does not prove when or whether ownership changed. |
| Bosch Global Software Technologies Vietnam | [Bosch Vietnam contact page](https://www.bosch.com.vn/contact/) and [Bosch Global Software Technologies Vietnam](https://www.bosch-softwaretechnologies.com/en/locations/vietnam/vechungtoi.html) | Use the software company's official Vietnam page. The supplied `https://www.bosch.com/vn` returned HTTP 404; Bosch's contact page points to the selected company-specific page. |

HTTP and TLS outcomes reflect the checking environment and time; websites can restrict automated access or change later. The pages are pointers for future research, not frozen evidence or an assertion that any later briefing claim is supported.
