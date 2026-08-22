# FrutraQ — Backend

A Django REST API for managing fruit transport logistics between rural collection points in Quindío, Colombia, and wholesale clients in Bogotá.

## The Problem

A small fruit transporter collects produce from multiple farms (weighed once on-site as a rough reference), delivers it to clients who re-weigh and classify it by quality (the weight that actually determines payment), and needs an auditable trail from collection to invoice — without losing historical accuracy when prices change over time.

## Tech Stack

- **Django 5.2 (LTS)** + **Django REST Framework**
- **djangorestframework-simplejwt** — JWT authentication
- **SQLite** (development) — PostgreSQL planned for production
- **python-decouple** — environment-based configuration

## Architecture & Key Decisions

- **UUID primary keys** on every model, to avoid exposing sequential record counts through the API.
- **Snapshot pricing pattern**: `DetalleEntrega` copies the price in effect at the moment of creation instead of holding a live foreign key to `PrecioCliente`. This keeps historical invoices accurate even after prices change.
- **Soft delete via `activo`**: `Producto`, `Proveedor`, and `Cliente` are deactivated, never deleted, to preserve referential integrity with historical records.
- **`CASCADE` vs `PROTECT`** used deliberately: child records that are meaningless without their parent (`PuntoRecoleccion` → `Viaje`) cascade; independent records that are merely referenced (`Proveedor`) are protected from deletion while in use.
- **Separate create/read serializers** for `DetalleEntrega`: the create endpoint only accepts product and weight — prices are always resolved server-side from the active `PrecioCliente`, so a client can never submit a manipulated price.
- **Explicit state machine** for `Viaje` status transitions (`RECOLECCION` → `TRANSITO` → `ENTREGADO`/`CANCELADO`), enforced in the view layer, preventing invalid jumps.
- **Fat models, thin views**: business logic (subtotal calculation, invoice numbering, price snapshotting) lives in the model layer, not scattered across views.
- Monetary values are always serialized as **strings** (e.g. `"250000.00"`) to avoid floating-point precision issues.

## Getting Started

```bash
git clone https://github.com/Juangxlvis/FrutraQ-Backend.git
cd frutraq-backend

python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows PowerShell

pip install -r requirements.txt
cp .env.example .env         # then fill in your own SECRET_KEY

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

API available at `http://127.0.0.1:8000/api/`. Admin panel at `http://127.0.0.1:8000/admin/`.

## Authentication

```
POST /api/token/          → obtain access + refresh JWT
POST /api/token/refresh/  → exchange refresh token for a new access token
```

All other endpoints require `Authorization: Bearer <access_token>`.

## Running Tests

```bash
python manage.py test core -v 2
```

Covers price-vigency resolution, subtotal calculation, invoice numbering, and the price-snapshot validation on `DetalleEntrega`.

## Project Status

Backend (Phase 1) complete: project setup, data models, admin, serializers, viewsets/routing, JWT auth, core business rules, and unit tests — 10/10 steps, 9/9 tests passing.

Frontend (Angular) is in active development in the companion [FrutraQ-Frontend](https://github.com/Juangxlvis/FrutraQ-Frontend) repository.

## License

Private project — not licensed for public reuse.
