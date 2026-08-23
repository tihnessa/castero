PRAGMA user_version=5;

create table download (
    ep_id  integer primary key,
    path   text not null unique,
    sha256 text not null,
    FOREIGN KEY (ep_id) REFERENCES episode(id) ON DELETE CASCADE
);
