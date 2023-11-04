CREATE TABLE ticket
(
    id            SERIAL PRIMARY KEY,
    uid           uuid UNIQUE NOT NULL,
    username      VARCHAR(80) NOT NULL,
    flight_number VARCHAR(20) NOT NULL,
    price         INT         NOT NULL,
    status        VARCHAR(20) NOT NULL CHECK (status IN ('PAID', 'CANCELED'))
);