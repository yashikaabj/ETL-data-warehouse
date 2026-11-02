-- Server-side COPY: the CSV folder must be visible to the Postgres server as /data
-- (docker-compose.yml mounts ./data there).
COPY src.phstate       FROM '/data/PHSTATE.csv'       WITH (FORMAT csv, HEADER true);
COPY src.phhq          FROM '/data/PHHQ.csv'          WITH (FORMAT csv, HEADER true);
COPY src.phparty_a     FROM '/data/PHPARTY_A.csv'     WITH (FORMAT csv, HEADER true);
COPY src.phitem        FROM '/data/PHITEM.csv'        WITH (FORMAT csv, HEADER true);
COPY src.phposting     FROM '/data/PHPOSTING.csv'     WITH (FORMAT csv, HEADER true);
COPY src.phpostingdet  FROM '/data/PHPOSTINGDET.csv'  WITH (FORMAT csv, HEADER true);
COPY src.employee      FROM '/data/EMPLOYEE.csv'      WITH (FORMAT csv, HEADER true);
