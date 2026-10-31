# India job coverage and expansion

AItlas searches jobs from its **configured employer registry**, not every employer on the internet. The defaults contain 42 public employer feeds and 40 additional official careers links. Jobs default to Hyderabad, Bengaluru/Bangalore, Pune and Chennai; city, role, employer text search and AI-role filters combine. Some existing boards also retain global roles, available through All locations. The newly added feeds retain only the four priority cities. A multi-location vacancy can appear under more than one city.

## Three distinct ways to find jobs

| Source | Inside AItlas search? | Application path |
|---|---|---|
| Connected Greenhouse, SmartRecruiters and Lever employer boards | Yes, after successful sync | Original employer ATS posting |
| Official careers links for additional employers | No | Employer careers site; refine location there |
| LinkedIn, Indeed, Naukri and Foundit city searches | No | Provider search with city/keyword hints, then verify the employer/requisition |

The directory reports connected, synced and failing employer counts separately. Zero matching indexed roles does not prove the employer has no vacancies. A careers-only entry has no numeric job count. Workday and proprietary career portals are deliberately not represented as indexed feeds without a supported adapter and permission to reuse their data.

The 23 new feeds include Experian, Western Digital, Arista Networks, Continental, Sutherland, Eurofins, Syngenta Group, Informa, New Relic, Elastic, Fivetran, PubMatic, InMobi, Zuora, 6sense, NICE, Samsara, Mindtickle, Coupa, CRED, Paytm, Meesho and Everseen. Additional careers links cover financial-services GCCs, healthcare, retail, semiconductors and other multinationals, including Citi, Bank of America, HSBC, Barclays, Optum, Target, Lowe’s, Novartis, Adobe, Cisco, Intel, Dell, Micron, Intuit, AMD and IBM. These are discovery candidates, not an employee-rated ranking or a claim that each currently has a vacancy in every target city.

## Reliable access to job data

1. **Employer feeds first.** The [Greenhouse Job Board API](https://developers.greenhouse.io/job-board.html), [SmartRecruiters public postings API](https://developers.smartrecruiters.com/reference/v1listpostings) and [Lever Postings API](https://github.com/lever/postings-api) supply employer-published vacancies. Public availability does not by itself grant unrestricted redistribution rights: review each provider's and employer's terms before a public deployment. Preserve source links, attribution and removal procedures.
2. **External saved searches for broad discovery.** LinkedIn prohibits unauthorized automated collection in its [prohibited software guidance](https://www.linkedin.com/help/linkedin/answer/a1341387/prohibited-software-and-extensions). Its [Job Posting API](https://learn.microsoft.com/en-us/linkedin/talent/job-postings/api/overview) is an approved-partner integration for posting jobs, not a general search API for downloading all vacancies. Indeed's [developer agreement](https://docs.indeed.com/legal-terms/developer-agreement-third-party) limits API use to approved purposes and restricts unauthorized collection and redistribution. AItlas does not scrape these services, import their listings, or use browser sessions/cookies. Use their own saved searches and alerts.
3. **Approved aggregator for broader automatic coverage.** Evaluate an India-capable provider such as [Adzuna](https://developer.adzuna.com/overview), obtain credentials and confirm display, caching, attribution, expiry and redistribution rights for this product. This integration is **not implemented**. Provider credentials belong in server-side secrets. A future adapter should record the origin employer and requisition ID, deduplicate across ATS and aggregator results, retain provider attribution/application URLs, and report which coverage came from the aggregator.

Naukri and Foundit are outbound search links only. Providers can change their URL filters; users may need to refine keywords or locations on the destination site. LinkedIn and Indeed links request recent postings, but AItlas cannot guarantee their search results or freshness.

## Availability and provenance

Feeds refresh every 60–120 minutes by default. The scheduler persists backoff, retries transient failures once and isolates a failed source. SmartRecruiters requests only PUBLIC India postings and exhausts pagination. Lever supports global and EU boards, paginates in batches of 100, rejects repeated IDs and unexpected posting hosts, and limits snapshots to 5,000 records. Partial or malformed paginated responses do not change availability. The common snapshot handler retires jobs only after two successful misses; transient failures preserve previous records and show a stale-data warning. An empty successful response counts as one miss.

Cards show when an item was checked. Dates distinguish employer publication/update timestamps from first observation by AItlas. Listings can close between refreshes; check the original posting before applying. AI relevance uses the role title and department, not general company AI marketing. This is a keyword heuristic, so review the actual requirements.

## Expanding employers without frontend changes

Run the operator CLI in `backend/` (or via the worker container):

```bash
uv run python -m app.sources add-source --id example-india-jobs --name 'Example India roles' --kind lever_jobs --url https://api.lever.co/v0/postings/example --interval 120 --options '{"company":"Example","target_cities_only":true}'
```

Replace the example with a verified public board. Use `api.eu.lever.co` for EU boards. The other accepted endpoint patterns are `https://boards-api.greenhouse.io/v1/boards/BOARD/jobs` and `https://api.smartrecruiters.com/v1/companies/COMPANY/postings`. Verify company identity, the public endpoint, city results and usage terms before enabling a source. Add defaults to `backend/config/sources.json` for fresh installations; `sync-defaults` inserts missing sources without overwriting operator edits. A new ATS family requires an adapter and failure/pagination tests.

Employer categories, official careers links and dated recognitions live in `backend/config/intelligence.json`. Employee ratings are not connected. Only selected recognitions have been verified: Arista's [2026 Fortune 500 announcement](https://www.arista.com/company/news/press-release/24401-pr-20260804), Western Digital's inclusion in the [2026 Fortune 500 list](https://www.fortune.com/ranking/fortune500/), and Experian's [2025 workplace recognition](https://www.experianplc.com/newsroom/press-releases/2025/experian-named-one-of-worlds-best-workplaces-for-second-consecutive-year). List membership and awards are dated evidence, not a guarantee about a specific team, office or job. Missing recognition metadata does not imply a company lacks recognition.
