# 056. Photo documentation (geotagged, timeline, 360 photos, drawing-pinned)

## What it does
Site photo documentation records progress, defects, hidden work before it is covered, and claim or dispute evidence. For a small contractor the essentials are:
- Upload from a phone, with the GPS position and capture time read automatically from the file's EXIF data.
- A date timeline per project ("what did the slab look like on the 12th?").
- A map view of where each photo was taken.
- 360° (equirectangular) photos for walkthroughs.
- Pins on a drawing sheet, so a photo sits at the spot on the plan where it was taken.
- Links from photos to punch items, field reports, RFIs and BOQ positions.

Commercial tools such as CompanyCam, OpenSpace and the Procore Photos tool sell this as their main product.

## Already in the codebase (with file paths)
- `backend/app/modules/documents/models.py`: the `ProjectPhoto` model (`oe_documents_photo`) has `gps_lat`, `gps_lon`, `taken_at`, `tags`, `category`, `thumbnail_path` and a JSON `metadata` field. The `Sheet` model stores drawing sheets with revisions. `DocumentBIMLink` links documents to BIM elements.
- `backend/app/modules/documents/router.py`: the endpoints `/photos/upload`, `/photos`, `/photos/gallery`, `/photos/timeline` (photos grouped by date), `/photos/{id}/file` and PATCH/DELETE.
- `backend/app/modules/documents/service.py`: Pillow thumbnails with `ImageOps.exif_transpose`. **Gap:** GPS and `taken_at` come from client form parameters. EXIF GPS and DateTimeOriginal are not read on the server.
- `frontend/src/features/documents/PhotoGalleryPage.tsx`: a gallery and timeline view, category filters and a location badge (MapPin).
- `backend/app/modules/punchlist/models.py` and `backend/app/modules/fieldreports/models.py`: each has a JSON `photos` list. These are not foreign keys to `ProjectPhoto`.
- **Missing:**
  - EXIF auto-extraction, including HEIC from iPhones.
  - A map view.
  - A 360° viewer and an `is_panorama` flag.
  - Photo pins on a `Sheet` (sheet id plus normalised x/y).
  - Before/after comparison.
  - A photo report export.
  - A validation rule (for example "a closed punch item needs a photo").

## Who it helps and how much
High value for small general contractors, renovation and remodel firms, and subcontractors who now use WhatsApp galleries or a separate paid photo app. Photos are the cheapest kind of evidence for change orders, delay claims, warranty disputes and progress billing. Having them inside the ERP, linked to BOQ and punch items, removes one subscription. Third-party listings put CompanyCam at roughly USD 60-200 per month. Estimators also use photos from site visits during takeoff. 360° and drawing pins are useful mainly for mid-size jobs, so they rank lower than EXIF, map and timeline for very small firms.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium** overall. Most of the work sits in `documents`, with small changes in `punchlist`, `fieldreports` and `reporting`.
1. **Small:** in `upload_photo`, read EXIF GPSInfo and DateTimeOriginal with the existing Pillow dependency (`Image.getexif().get_ifd(ExifTags.IFD.GPSInfo)`). Client values override EXIF. Register `pillow-heif` as an optional plugin.
2. **Small:** add `is_panorama` to `ProjectPhoto`, detected from the XMP `GPano:ProjectionType` tag or a 2:1 aspect ratio. Render panoramas with Photo Sphere Viewer, which already uses Three.js, part of the existing stack.
3. **Medium:** add a `PhotoPin` table (`photo_id`, `sheet_id`, `x`, `y` normalised 0-1) and an overlay on the existing PDF.js sheet viewer (`markups`/`takeoff` canvas).
4. **Small:** a map tab using Leaflet with OpenStreetMap tiles; the tile server URL should be configurable.
5. Publish events (`documents.photo.uploaded`) on the event bus so `fieldreports` and `punchlist` can attach photos by id. Add a `photo_evidence` validation rule and a PDF photo report in `reporting`.
6. **Optional:** an `integrations` connector that imports photos from CompanyCam via its v2 REST API (bearer token).

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- Pillow ExifTags (already a dependency; MIT-CMU licence): https://pillow.readthedocs.io/en/stable/reference/ExifTags.html
- pillow-heif, HEIC support (BSD-3-Clause; bundled codecs carry their own licences): https://github.com/bigcat88/pillow_heif
- exifr, client-side EXIF/GPS reading before upload (MIT): https://github.com/MikeKovarik/exifr
- Photo Sphere Viewer, 360° viewer built on Three.js, with a markers plugin (MIT): https://photo-sphere-viewer.js.org/
- Pannellum, a lighter 360° alternative (MIT): https://pannellum.org/
- Leaflet maps (BSD-2-Clause): https://leafletjs.com/. OpenStreetMap tiles are subject to a usage policy, so production use needs a self-hosted or commercial tile server: https://operations.osmfoundation.org/policies/tiles/
- CompanyCam API v2 (requires a paid CompanyCam plan; official pricing not verified): https://docs.companycam.com/
- CompanyCam MCP servers: a community MIT server and hosted versions (Zapier, Composio). These are unofficial; I did not verify that any of them is maintained: https://glama.ai/mcp/servers/j95eb5wsco, https://zapier.com/mcp/companycam
- I could not verify any open-source MCP server for generic construction photo management.

## Priority: 4/5 — core gallery exists; EXIF auto-extract, map, sheet pins and 360 viewer are cheap, high-visibility gaps that replace a paid app
The foundation is already built. Each gap can be filled with a permissively licensed library, and the result replaces a standalone photo subscription for small firms.

## Sources
- https://pillow.readthedocs.io/en/stable/reference/ExifTags.html
- https://github.com/bigcat88/pillow_heif
- https://github.com/MikeKovarik/exifr
- https://www.npmjs.com/package/@photo-sphere-viewer/core
- https://photo-sphere-viewer.js.org/
- https://pannellum.org/
- https://leafletjs.com/
- https://operations.osmfoundation.org/policies/tiles/
- https://docs.companycam.com/changelog/add-tags-when-uploading-a-photo-to-a-project
- https://pricingsaas.com/companies/companycam
- https://glama.ai/mcp/servers/j95eb5wsco
- https://zapier.com/mcp/companycam
