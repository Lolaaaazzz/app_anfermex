CREATE DATABASE IF NOT EXISTS Sedena;

-- Usar Base de datos --
USE Sedena;
-- Usar Base de datos --

-- ========================================
-- Insertar EMPRESAS
-- ========================================
INSERT INTO Empresas (nombre_empresa) VALUES
('Transportes del Norte'),
('Logística Minera MX'),
('Camiones Sedena');

-- ========================================
-- Insertar USUARIOS
-- ========================================
INSERT INTO Usuarios (nombre_usuario, contrasena, rol)
VALUES 
('admin1', SHA2('admin123', 256), 'admin'),
('supervisor1', SHA2('super123', 256), 'supervisor'),
('operador1', SHA2('operador123', 256), 'operador');

-- ========================================
-- Insertar OPERADORES
-- ========================================
INSERT INTO Operadores (numero_operador, numero_telefono, nombre_operador, id_empresa, placas_tractocamion, placas_gondola1, placas_gondola2)
VALUES 
(101, '5551234567', 'Luis Gómez', 1, 'TRN-001', 'GND-001', 'GND-002'),
(102, '5559876543', 'María López', 2, 'LOG-123', 'GND-101', 'GND-102');

-- ========================================
-- Insertar CARGAS Y DESCARGAS
-- ========================================
INSERT INTO CargasDescargas (id_operador, folio, fecha_carga, hora_carga, destino, nombre_operador, placas_tractocamion, placas_gondola1, placas_gondola2, total_m3_cargados, id_empresa)
VALUES 
(101, 'F001', '2025-05-21', '08:00:00', 'Obra Norte', 'Luis Gómez', 'TRN-001', 'GND-001', 'GND-002', 60.0, 1),
(102, 'F002', '2025-05-21', '09:30:00', 'Obra Centro', 'María López', 'LOG-123', 'GND-101', 'GND-102', 58.5, 2);

-- ========================================
-- Insertar DESCARGAS
-- ========================================
INSERT INTO Descargas (id_carga, fecha_descarga, hora_descarga, destino, m3_cargados, m3_descargados, id_empresa, observaciones)
VALUES 
(1, '2025-05-21', '10:30:00', 'Obra Norte', 60.0, 59.0, 1, 'Ligeramente menor por compactación'),
(2, '2025-05-21', '11:45:00', 'Obra Centro', 58.5, 58.0, 2, 'Sin variaciones importantes');

SELECT o.numero_operador, o.nombre_operador, e.nombre_empresa
FROM Operadores o
JOIN Empresas e ON o.id_empresa = e.id_empresa;

SELECT c.folio, o.nombre_operador, e.nombre_empresa, c.total_m3_cargados
FROM CargasDescargas c
JOIN Operadores o ON c.id_operador = o.numero_operador
JOIN Empresas e ON c.id_empresa = e.id_empresa;

ALTER TABLE empresas
ADD COLUMN plazo_credito_dias INT DEFAULT 10 COMMENT 'Plazo de crédito estándar en días para esta empresa';

ALTER TABLE cargasdescargas
ADD COLUMN fecha_limite_pago DATE NULL COMMENT 'Fecha límite para liquidar el crédito de esta carga';

ALTER TABLE cargasdescargas
ADD COLUMN estado_pago VARCHAR(20) DEFAULT 'VIGENTE' COMMENT 'Estado del crédito: VIGENTE, POR VENCER, VENCIDO, PAGADO';

-- 1. Añadir nombre_operador_descarga
ALTER TABLE descargas
ADD COLUMN nombre_operador_descarga VARCHAR(100) NULL 
COMMENT 'Nombre del operador que realizó la descarga.'
AFTER id_empresa; -- O donde prefieras que aparezca la columna

-- 2. Añadir placas_gondola1_descarga
ALTER TABLE descargas
ADD COLUMN placas_gondola1_descarga VARCHAR(20) NULL 
COMMENT 'Placas de la góndola 1 al momento de la descarga.'
AFTER nombre_operador_descarga; -- O donde prefieras

-- 3. Añadir placas_gondola2_descarga
ALTER TABLE descargas
ADD COLUMN placas_gondola2_descarga VARCHAR(20) NULL 
COMMENT 'Placas de la góndola 2 al momento de la descarga.'
AFTER placas_gondola1_descarga; -- O donde prefieras

-- 4. Añadir codigo_barras_ticket_descarga
ALTER TABLE descargas
ADD COLUMN codigo_barras_ticket_descarga VARCHAR(255) NULL 
COMMENT 'Código de barras del ticket o comprobante de la descarga.'
AFTER observaciones; -- O donde prefieras

ALTER TABLE operadores 
CHANGE COLUMN total_m3_acumulado capacidad_carga_m3 DECIMAL(10,2) DEFAULT '0.00' 
COMMENT 'Capacidad de carga típica o estándar en m3 para este operador';

-- Registrar nuevo usuario --
-- Usuario Admin --
INSERT INTO Usuarios (nombre_usuario, contrasena, rol) 
VALUES (
    'Aldrin_RV', 
    SHA2('ALdrinruiz01', 256), 
    'admin'
);

-- COMANDOS UTILIZADOS -- 

-- seleccionar tablas --
Select * from Operadores;
Select * from Empresas;
Select * from Usuarios;
Select * from Cargasdescargas; -- cargas 
Select * from Descargas;
-- Seleccion de tablas --

-- Ver solo el nombre y teléfono de los operadores
SELECT nombre_operador, numero_telefono FROM operadores;

-- Buscar una carga específica por su folio
SELECT * FROM cargasdescargas WHERE folio = 'F001';

-- Ver todos los operadores de una empresa específica (ej. id_empresa = 1)
SELECT * FROM operadores WHERE id_empresa = 1;

-- Ver las cargas realizadas en una fecha específica
SELECT * FROM cargasdescargas WHERE fecha_carga = '2025-05-21';

-- Ver las cargas con estado_pago 'VENCIDO'
SELECT * FROM cargasdescargas WHERE estado_pago = 'VENCIDO';

-- Buscar operadores cuyo nombre contenga "Gómez"
SELECT * FROM operadores WHERE nombre_operador LIKE '%Gómez%';

-- Ver detalles de cargas con el nombre de la empresa y el nombre del operador
SELECT 
    c.folio, c.fecha_carga, c.total_m3_cargados, 
    o.nombre_operador, o.placas_tractocamion,
    e.nombre_empresa
FROM cargasdescargas c
JOIN operadores o ON c.id_operador = o.numero_operador
JOIN empresas e ON c.id_empresa = e.id_empresa
WHERE c.folio = 'F001'; -- Puedes añadir un WHERE para filtrar

-- Ver detalles de descargas, incluyendo el folio de la carga original
SELECT 
    d.*, 
    c.folio as folio_carga_original
FROM descargas d
JOIN cargasdescargas c ON d.id_carga = c.id_carga
WHERE d.id_descarga = 1; -- Ejemplo para una descarga específica

-- Total de cargas y volumen total cargado por día
SELECT 
    fecha_carga, 
    COUNT(id_carga) AS numero_de_cargas, 
    SUM(total_m3_cargados) AS volumen_total_cargado_ese_dia
FROM cargasdescargas
GROUP BY fecha_carga
ORDER BY fecha_carga DESC; -- Ordena por fecha descendente

-- Total de descargas y volumen total descargado por empresa
SELECT 
    id_empresa, 
    COUNT(id_descarga) AS numero_de_descargas,
    SUM(m3_descargados) AS volumen_total_descargado_por_empresa
FROM descargas
GROUP BY id_empresa;

-- Ver todas las cargas ordenadas por fecha, de la más reciente a la más antigua
SELECT * FROM cargasdescargas ORDER BY fecha_carga DESC, hora_carga DESC;

-- Añadir una nueva empresa
INSERT INTO empresas (nombre_empresa, plazo_credito_dias) 
VALUES ('Transportes Rápidos del Sur', 15);

-- Añadir un nuevo operador
INSERT INTO operadores (numero_operador, nombre_operador, id_empresa, placas_tractocamion, capacidad_carga_m3, numero_telefono) 
VALUES (103, 'Ana Torres', 2, 'ANA-001', 22.50, '5550001122');

-- Añadir un nuevo usuario (recuerda hashear la contraseña)
INSERT INTO usuarios (nombre_usuario, contrasena, rol) 
VALUES ('operador_nuevo', SHA2('nueva_clave_123', 256), 'operador');

-- Añadir una nueva carga (asegúrate de que id_operador e id_empresa existan)
-- Nota: fecha_limite_pago y estado_pago se pueden calcular/establecer aquí también.
-- Para fecha_limite_pago, necesitarías obtener el plazo_credito_dias de la empresa.
-- Esto es más fácil de hacer desde un script (Python) que con SQL puro en un solo INSERT,
-- o usando un TRIGGER en la base de datos.
-- Ejemplo básico sin cálculo automático de fecha_limite_pago:
INSERT INTO cargasdescargas (
    id_operador, folio, fecha_carga, hora_carga, destino, 
    nombre_operador, placas_tractocamion, placas_gondola1, placas_gondola2, 
    total_m3_cargados, id_empresa, estado_pago, fecha_limite_pago
) VALUES (
    101, 'F003', CURDATE(), CURTIME(), 'Obra Sureste', 
    'Luis Gómez', 'TRN-001', 'GND-001', 'GND-002', 
    55.0, 1, 'VIGENTE', DATE_ADD(CURDATE(), INTERVAL 10 DAY) -- Ejemplo de cálculo de fecha límite
);

-- Actualizar el número de teléfono de un operador
UPDATE operadores 
SET numero_telefono = '555-111-2233' 
WHERE numero_operador = 101;

-- Cambiar el estado de pago de una carga a 'PAGADO'
UPDATE cargasdescargas 
SET estado_pago = 'PAGADO' 
WHERE id_carga = 1; -- O podrías usar WHERE folio = 'F001';

-- Actualizar la capacidad de carga típica de un operador
UPDATE operadores
SET capacidad_carga_m3 = 25.00
WHERE numero_operador = 102;

-- Eliminar un usuario específico (¡con cuidado!)
DELETE FROM usuarios 
WHERE nombre_usuario = 'usuario_a_borrar';

-- Eliminar una descarga específica (¡con cuidado!)
-- Si hay otras tablas que referencian esta descarga con llaves foráneas, podría fallar
-- o tener efectos en cascada dependiendo de la configuración de esas llaves.
DELETE FROM descargas 
WHERE id_descarga = 3;

--  COMANDOS UTILIZADOS -- 
-------------
-------------

-- 1. CREAR Y USAR LA BASE DE DATOS
CREATE DATABASE IF NOT EXISTS `Sedena` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE `Sedena`;

-- 2. BORRAR TABLAS SI EXISTEN (para empezar con una estructura limpia)
DROP TABLE IF EXISTS `descargas`;
DROP TABLE IF EXISTS `cargasdescargas`;
DROP TABLE IF EXISTS `usuarios`;
DROP TABLE IF EXISTS `operadores`;
DROP TABLE IF EXISTS `empresas`;

-- 3. CREAR LAS TABLAS CON LA ESTRUCTURA CORRECTA Y FINAL

-- Tabla Empresas
CREATE TABLE `empresas` (
  `id_empresa` INT NOT NULL AUTO_INCREMENT,
  `nombre_empresa` VARCHAR(100) NOT NULL,
  `plazo_credito_dias` INT DEFAULT 10 COMMENT 'Plazo de crédito estándar en días para esta empresa',
  PRIMARY KEY (`id_empresa`),
  UNIQUE KEY `uq_nombre_empresa` (`nombre_empresa`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Tabla Operadores
CREATE TABLE `operadores` (
  `numero_operador` INT NOT NULL,
  `nombre_operador` VARCHAR(100) NOT NULL,
  `numero_telefono` VARCHAR(20) DEFAULT NULL,
  `id_empresa` INT NOT NULL,
  `placas_tractocamion` VARCHAR(20) DEFAULT NULL,
  `placas_gondola1` VARCHAR(20) DEFAULT NULL,
  `placas_gondola2` VARCHAR(20) DEFAULT NULL,
  `capacidad_carga_m3` DECIMAL(10,2) DEFAULT '0.00' COMMENT 'Capacidad de carga típica o estándar en m3 para este operador',
  PRIMARY KEY (`numero_operador`),
  KEY `fk_operadores_empresas_idx` (`id_empresa`),
  CONSTRAINT `fk_operadores_empresas` FOREIGN KEY (`id_empresa`) REFERENCES `empresas` (`id_empresa`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Tabla Usuarios
CREATE TABLE `usuarios` (
  `id_usuario` INT NOT NULL AUTO_INCREMENT,
  `nombre_usuario` VARCHAR(50) NOT NULL,
  `contrasena` VARCHAR(255) NOT NULL COMMENT 'Contraseña hasheada con SHA256',
  `rol` ENUM('admin','supervisor','operador') DEFAULT 'operador',
  `fecha_creacion` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_usuario`),
  UNIQUE KEY `uq_nombre_usuario` (`nombre_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Tabla CargasDescargas (Cargas)
CREATE TABLE `cargasdescargas` (
  `id_carga` INT NOT NULL AUTO_INCREMENT,
  `folio` VARCHAR(50) NOT NULL,
  `fecha_carga` DATE NOT NULL,
  `hora_carga` TIME DEFAULT NULL,
  `id_operador` INT NOT NULL COMMENT 'FK a operadores.numero_operador',
  `nombre_operador` VARCHAR(100) DEFAULT NULL COMMENT 'Snapshot del nombre del operador al momento de la carga',
  `placas_tractocamion` VARCHAR(20) DEFAULT NULL COMMENT 'Snapshot de placas tracto al momento de la carga',
  `placas_gondola1` VARCHAR(20) DEFAULT NULL COMMENT 'Snapshot de placas góndola 1 al momento de la carga',
  `placas_gondola2` VARCHAR(20) DEFAULT NULL COMMENT 'Snapshot de placas góndola 2 al momento de la carga',
  `id_empresa` INT NOT NULL COMMENT 'FK a empresas.id_empresa',
  `destino` VARCHAR(100) NOT NULL,
  `total_m3_cargados` DECIMAL(10,2) NOT NULL, -- Columna correcta para el volumen
  `estado_pago` VARCHAR(20) DEFAULT 'VIGENTE' COMMENT 'Estado del crédito: VIGENTE, POR VENCER, VENCIDO, PAGADO',
  `fecha_limite_pago` DATE DEFAULT NULL COMMENT 'Fecha límite para liquidar el crédito de esta carga',
  PRIMARY KEY (`id_carga`),
  UNIQUE KEY `uq_folio_carga` (`folio`),
  KEY `fk_cargas_operadores_idx` (`id_operador`),
  KEY `fk_cargas_empresas_idx` (`id_empresa`),
  KEY `idx_fecha_carga` (`fecha_carga`),
  CONSTRAINT `fk_cargas_operadores` FOREIGN KEY (`id_operador`) REFERENCES `operadores` (`numero_operador`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_cargas_empresas` FOREIGN KEY (`id_empresa`) REFERENCES `empresas` (`id_empresa`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Tabla Descargas
CREATE TABLE `descargas` (
  `id_descarga` INT NOT NULL AUTO_INCREMENT,
  `id_carga` INT NOT NULL COMMENT 'FK a cargasdescargas.id_carga',
  `fecha_descarga` DATE NOT NULL,
  `hora_descarga` TIME DEFAULT NULL,
  `destino` VARCHAR(100) NOT NULL COMMENT 'Destino de esta descarga',
  `m3_cargados` DECIMAL(10,2) NOT NULL COMMENT 'Volumen que venía en la carga original (informativo)',
  `m3_descargados` DECIMAL(10,2) NOT NULL COMMENT 'Volumen realmente descargado',
  `id_empresa` INT NOT NULL COMMENT 'FK a empresas.id_empresa (asociada a esta descarga)',
  `nombre_operador_descarga` VARCHAR(100) DEFAULT NULL COMMENT 'Snapshot del nombre del operador que realizó la descarga',
  `placas_gondola1_descarga` VARCHAR(20) DEFAULT NULL COMMENT 'Snapshot de placas góndola 1 al momento de la descarga',
  `placas_gondola2_descarga` VARCHAR(20) DEFAULT NULL COMMENT 'Snapshot de placas góndola 2 al momento de la descarga',
  `observaciones` TEXT,
  `codigo_barras_ticket_descarga` VARCHAR(255) DEFAULT NULL COMMENT 'Código de barras del ticket o comprobante de la descarga',
  PRIMARY KEY (`id_descarga`),
  KEY `fk_descargas_cargas_idx` (`id_carga`),
  KEY `fk_descargas_empresas_idx` (`id_empresa`),
  CONSTRAINT `fk_descargas_cargas` FOREIGN KEY (`id_carga`) REFERENCES `cargasdescargas` (`id_carga`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_descargas_empresas` FOREIGN KEY (`id_empresa`) REFERENCES `empresas` (`id_empresa`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 4. INSERTAR DATOS DE EJEMPLO (Los que tenías en tu archivo Sedena.sql, sin los "_N")
INSERT INTO `empresas` (`nombre_empresa`, `plazo_credito_dias`) VALUES
('Transportes del Norte', 15),
('Logística Minera MX', 20),
('Camiones Sedena', 10);

INSERT INTO `operadores` (`numero_operador`, `nombre_operador`, `numero_telefono`, `id_empresa`, `placas_tractocamion`, `placas_gondola1`, `placas_gondola2`, `capacidad_carga_m3`) VALUES
(101, 'Luis Gómez', '5551234567', 1, 'TRN-001', 'GND-001A', 'GND-002A', 28.50),
(102, 'María López', '5559876543', 2, 'LOG-123', 'GND-101B', NULL, 30.00),
(103, 'Carlos Sánchez', '5555550000', 1, 'TRN-002', 'GND-003A', NULL, 29.00); -- Asumí que este es un nuevo operador que podrías querer

INSERT INTO `usuarios` (`nombre_usuario`, `contrasena`, `rol`) VALUES 
('Aldrin_RV', SHA2('ALdrinruiz01', 256), 'admin'), 
('supervisor1', SHA2('super123', 256), 'supervisor'), -- Mantengo estos si los quieres
('operador1', SHA2('operador123', 256), 'operador');   -- Mantengo estos si los quieres

INSERT INTO `cargasdescargas` (`id_operador`, `folio`, `fecha_carga`, `hora_carga`, `destino`, `nombre_operador`, `placas_tractocamion`, `placas_gondola1`, `placas_gondola2`, `total_m3_cargados`, `id_empresa`, `estado_pago`, `fecha_limite_pago`) VALUES 
(101, 'F001', '2025-05-21', '08:00:00', 'Obra Norte', 'Luis Gómez', 'TRN-001', 'GND-001A', 'GND-002A', 60.0, 1, 'VIGENTE', DATE_ADD('2025-05-21', INTERVAL (SELECT plazo_credito_dias FROM empresas WHERE id_empresa = 1) DAY)),
(102, 'F002', '2025-05-21', '09:30:00', 'Obra Centro', 'María López', 'LOG-123', 'GND-101B', NULL, 58.5, 2, 'VIGENTE', DATE_ADD('2025-05-21', INTERVAL (SELECT plazo_credito_dias FROM empresas WHERE id_empresa = 2) DAY));

INSERT INTO `descargas` (`id_carga`, `fecha_descarga`, `hora_descarga`, `destino`, `m3_cargados`, `m3_descargados`, `id_empresa`, `observaciones`, `nombre_operador_descarga`, `placas_gondola1_descarga`, `placas_gondola2_descarga`, `codigo_barras_ticket_descarga`) VALUES 
(1, '2025-05-21', '10:30:00', 'Obra Norte', 60.0, 59.0, 1, 'Ligeramente menor por compactación', 'Luis Gómez', 'GND-001A', 'GND-002A', 'TICKET_001'),
(2, '2025-05-21', '11:45:00', 'Obra Centro', 58.5, 58.0, 2, 'Sin variaciones importantes', 'María López', 'GND-101B', NULL, 'TICKET_002');

USE Sedena;

ALTER TABLE empresas
ADD COLUMN numero_cuenta_bancaria VARCHAR(50) NULL 
COMMENT 'Número de cuenta bancaria para depósitos a la empresa'
AFTER plazo_credito_dias; -- O donde prefieras que aparezca la columna

USE Sedena;

ALTER TABLE empresas
ADD COLUMN banco VARCHAR(100) NULL 
COMMENT 'Nombre de la institución bancaria de la cuenta'
AFTER numero_cuenta_bancaria; -- O donde prefieras que aparezca la columna

-- ==================================================================================
-- EJEMPLOS DE CONSULTAS Y COMANDOS DE MODIFICACIÓN (COMENTADOS PARA REFERENCIA)
-- (Estos son los comandos que tenías en tu archivo Sedena.sql como ejemplos o
--  ALTERs intermedios. Los he comentado para que no se ejecuten pero los tengas.)
-- ==================================================================================

-- -- Ver solo el nombre y teléfono de los operadores
-- SELECT nombre_operador, numero_telefono FROM operadores;

-- -- Buscar una carga específica por su folio
-- SELECT * FROM cargasdescargas WHERE folio = 'F001';

-- -- Ver todos los operadores de una empresa específica (ej. id_empresa = 1)
-- SELECT * FROM operadores WHERE id_empresa = 1;

-- -- Ver las cargas realizadas en una fecha específica
-- SELECT * FROM cargasdescargas WHERE fecha_carga = '2025-05-21';

-- -- Ver las cargas con estado_pago 'VENCIDO'
-- SELECT * FROM cargasdescargas WHERE estado_pago = 'VENCIDO';

-- -- Buscar operadores cuyo nombre contenga "Gómez"
-- SELECT * FROM operadores WHERE nombre_operador LIKE '%Gómez%';

-- -- Ver detalles de cargas con el nombre de la empresa y el nombre del operador
-- SELECT 
--     c.folio, c.fecha_carga, c.total_m3_cargados, 
--     o.nombre_operador, o.placas_tractocamion,
--     e.nombre_empresa
-- FROM cargasdescargas c
-- JOIN operadores o ON c.id_operador = o.numero_operador
-- JOIN empresas e ON c.id_empresa = e.id_empresa
-- WHERE c.folio = 'F001'; -- Puedes añadir un WHERE para filtrar

-- -- Ver detalles de descargas, incluyendo el folio de la carga original
-- SELECT 
--     d.*, 
--     c.folio as folio_carga_original
-- FROM descargas d
-- JOIN cargasdescargas c ON d.id_carga = c.id_carga
-- WHERE d.id_descarga = 1; -- Ejemplo para una descarga específica

-- -- Total de cargas y volumen total cargado por día
-- SELECT 
--     fecha_carga, 
--     COUNT(id_carga) AS numero_de_cargas, 
--     SUM(total_m3_cargados) AS volumen_total_cargado_ese_dia
-- FROM cargasdescargas
-- GROUP BY fecha_carga
-- ORDER BY fecha_carga DESC; -- Ordena por fecha descendente

-- -- Total de descargas y volumen total descargado por empresa
-- SELECT 
--     id_empresa, 
--     COUNT(id_descarga) AS numero_de_descargas,
--     SUM(m3_descargados) AS volumen_total_descargado_por_empresa
-- FROM descargas
-- GROUP BY id_empresa;

-- -- Ver todas las cargas ordenadas por fecha, de la más reciente a la más antigua
-- SELECT * FROM cargasdescargas ORDER BY fecha_carga DESC, hora_carga DESC;

-- -- Añadir una nueva empresa (ejemplo, ya se hace arriba con datos)
-- -- INSERT INTO empresas (nombre_empresa, plazo_credito_dias) 
-- -- VALUES ('Transportes Rápidos del Sur', 15);

-- -- Añadir un nuevo operador (ejemplo, ya se hace arriba con datos)
-- -- INSERT INTO operadores (numero_operador, nombre_operador, id_empresa, placas_tractocamion, capacidad_carga_m3, numero_telefono) 
-- -- VALUES (103, 'Ana Torres', 2, 'ANA-001', 22.50, '5550001122');

-- -- Añadir una nueva carga (ejemplo, ya se hace arriba con datos)
-- -- INSERT INTO cargasdescargas (
-- --     id_operador, folio, fecha_carga, hora_carga, destino, 
-- --     nombre_operador, placas_tractocamion, placas_gondola1, placas_gondola2, 
-- --     total_m3_cargados, id_empresa, estado_pago, fecha_limite_pago
-- -- ) VALUES (
-- --     101, 'F003', CURDATE(), CURTIME(), 'Obra Sureste', 
-- --     'Luis Gómez', 'TRN-001', 'GND-001', 'GND-002', 
-- --     55.0, 1, 'VIGENTE', DATE_ADD(CURDATE(), INTERVAL 10 DAY) 
-- -- );

-- -- Actualizar el número de teléfono de un operador
-- UPDATE operadores 
-- SET numero_telefono = '555-111-2233' 
-- WHERE numero_operador = 101;

-- -- Cambiar el estado de pago de una carga a 'PAGADO'
-- UPDATE cargasdescargas 
-- SET estado_pago = 'PAGADO' 
-- WHERE id_carga = 1; -- O podrías usar WHERE folio = 'F001';

-- -- Actualizar la capacidad de carga típica de un operador
-- UPDATE operadores
-- SET capacidad_carga_m3 = 25.00
-- WHERE numero_operador = 102;

-- -- Eliminar un usuario específico (¡con cuidado!)
-- -- DELETE FROM usuarios 
-- -- WHERE nombre_usuario = 'usuario_a_borrar';

-- -- Eliminar una descarga específica (¡con cuidado!)
-- -- DELETE FROM descargas 
-- -- WHERE id_descarga = 3;

-- -- ALTERs que tenías en tu script (ahora son parte de los CREATE TABLE de arriba)
-- -- ALTER TABLE empresas
-- -- ADD COLUMN plazo_credito_dias INT DEFAULT 10 COMMENT 'Plazo de crédito estándar en días para esta empresa';

-- -- ALTER TABLE cargasdescargas
-- -- ADD COLUMN fecha_limite_pago DATE NULL COMMENT 'Fecha límite para liquidar el crédito de esta carga';

-- -- ALTER TABLE cargasdescargas
-- -- ADD COLUMN estado_pago VARCHAR(20) DEFAULT 'VIGENTE' COMMENT 'Estado del crédito: VIGENTE, POR VENCER, VENCIDO, PAGADO';

-- -- ALTER TABLE descargas
-- -- ADD COLUMN nombre_operador_descarga VARCHAR(100) NULL 
-- -- COMMENT 'Nombre del operador que realizó la descarga.'
-- -- AFTER id_empresa;

-- -- ALTER TABLE descargas
-- -- ADD COLUMN placas_gondola1_descarga VARCHAR(20) NULL 
-- -- COMMENT 'Placas de la góndola 1 al momento de la descarga.'
-- -- AFTER nombre_operador_descarga; 

-- -- ALTER TABLE descargas
-- -- ADD COLUMN placas_gondola2_descarga VARCHAR(20) NULL 
-- -- COMMENT 'Placas de la góndola 2 al momento de la descarga.'
-- -- AFTER placas_gondola1_descarga; 

-- -- ALTER TABLE descargas
-- -- ADD COLUMN codigo_barras_ticket_descarga VARCHAR(255) NULL 
-- -- COMMENT 'Código de barras del ticket o comprobante de la descarga.'
-- -- AFTER observaciones; 

-- -- ALTER TABLE operadores 
-- -- CHANGE COLUMN total_m3_acumulado capacidad_carga_m3 DECIMAL(10,2) DEFAULT '0.00' 
-- -- COMMENT 'Capacidad de carga típica o estándar en m3 para este operador';