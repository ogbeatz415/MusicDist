# Turn release preparation into real distribution

## Current boundary

MusicDist prepares an internal handoff package for any of the selected planning destinations. No destination is connected. There is no generic SFTP destination or universal XML file that grants distribution access. No Apple, Spotify or other provider credential is included or fabricated.

## Obtain from your first partner or direct DSP

- Written/portal approval and the scope of your distribution account.
- Whether the interface supports your intended own-brand, multi-artist service.
- Current API/package specification or exact DDEX ERN version AND release profile.
- Sandbox/onboarding endpoint and approved test procedure.
- Real sender and recipient identifiers; authentication requirements.
- Required audio/artwork/credits, genres, language and territory mappings.
- Submission idempotency, checksums, upload completion markers, acknowledgment format.
- Release lead times and scheduling rules.
- Procedures for metadata updates, audio replacements, takedowns and redelivery.
- Delivery reports, store identifiers/URLs, royalties/reporting access and payout responsibilities.

A normal artist distribution subscription does not by itself establish an API or sublicensing arrangement for your own distribution platform; confirm the provider's offered integration and commercial terms.

## Implement the first approved adapter

1. Map the canonical MusicDist release and asset hashes into the recipient's exact schema.
2. Validate the recipient schema/profile locally; for DDEX, use the actual XSD and recipient-specific checks. Obtain the required DDEX implementation licence before going live.
3. Create a durable delivery job keyed by release version + recipient. Never mark a delivery successful just because a file uploaded.
4. Upload masters/artwork and metadata through the approved protocol. Verify SFTP host keys if applicable; use dedicated secrets and never invent an Apple hostname.
5. Record acknowledgments and rejection details; retry safely without duplicate releases.
6. Reconcile accepted/live status and recipient release/track IDs.
7. Complete an agreed test delivery before sending the catalog.
8. Add each further adapter against that recipient's supported interface; retain a shared release catalog.

Recommended future state names: prepared → queued → submitted → accepted/rejected → live; updates and takedowns need separate versioned jobs. These future states are design guidance, not implemented delivery claims.

## Owner decisions still needed

- Distribution partner/API or direct DSP onboarding?
- Your legal label/distributor name and assigned identifiers.
- Existing ISRC/UPC inventory for these recordings/releases.
- Which real release to use as the first test and which territories you control.

## References

Apple delivery tools: https://itunespartner.apple.com/music/support/5221-music-delivery-tools
Apple audio source specification: https://help.apple.com/itc/videoaudioassetguide/en.lproj/static.html
DDEX ERN guidance: https://kb.ddex.net/implementing-each-standard/electronic-release-notification-message-suite-(ern)/
ISRC identification guidance: https://usisrc.org/guidance-support/

These sources guide onboarding. The package itself has not been certified by a DSP or DDEX.
