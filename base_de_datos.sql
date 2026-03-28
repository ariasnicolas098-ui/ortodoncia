-- Pacientes
CREATE TABLE pacientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_completo TEXT NOT NULL,
    dni TEXT UNIQUE,
    fecha_nacimiento DATE,
    telefono TEXT,
    email TEXT,
    direccion TEXT,
    alergias TEXT,
    medicamentos_actuales TEXT,
    condiciones_medicas TEXT,
    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Historial Odontológico
CREATE TABLE historial_odontologico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER,
    fecha_consulta DATE,
    motivo_consulta TEXT,
    diagnostico TEXT,
    tratamiento_realizado TEXT,
    dientes_tratados TEXT,
    procedimiento TEXT,
    observaciones TEXT,
    proxima_cita DATE,
    odontologo TEXT,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
);

-- Radiografías/Archivos (opcional)
CREATE TABLE archivos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER,
    tipo TEXT, -- 'radiografia', 'foto', 'documento'
    ruta_archivo TEXT,
    descripcion TEXT,
    fecha_subida DATETIME DEFAULT CURRENT_TIMESTAMP
);