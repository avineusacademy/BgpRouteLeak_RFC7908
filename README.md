# BGP Route Leak Lab (RFC 7908 Types 1–6)

## Usage

1. Build and start services:
docker-compose build
docker-compose up


2. Visit: `http://localhost:8501`

3. In UI:
   - Select **Leak Type**.
   - Click **Apply Leak**.
   - See graph (red edges = leaked).
   - View BGP table on R2.
   - Click **Export PDF Report** to save output in `exports/`.

## Development

- `routers/R2/` contains configs per leak type.
- `scripts/apply_leak.sh` applies config and reloads BGP.
