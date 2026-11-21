# Rewrite a plain pg_dump of the public.nba_* tables so every object lands in schema nba_stage.
# DDL lines: public. -> nba_stage.  COPY headers likewise.  COPY data rows are passed through untouched.
BEGIN { print "CREATE SCHEMA nba_stage;" }
inb { print; if ($0 == "\\.") inb = 0; next }
/^COPY public\./ { sub(/^COPY public\./, "COPY nba_stage."); print; inb = 1; next }
{ gsub(/public\./, "nba_stage."); print }
