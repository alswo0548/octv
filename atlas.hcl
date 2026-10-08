// OCTV: existing SQL files stay the single source of truth.
// scripts/atlas_db.py generates the Atlas-compatible SQL file automatically.
env "local" {
  url = getenv("OCTV_ATLAS_DB_URL")
  dev = "docker://postgres/17/dev?search_path=public"
  schema {
    src = "file://database/.atlas_generated/schema.sql"
  }
  migration {
    dir = "file://database/atlas_migrations"
  }
}
