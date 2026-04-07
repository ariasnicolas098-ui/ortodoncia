import sqlite3

def init_db():
    conn = sqlite3.connect('consultorio_dental.db')
    cursor = conn.cursor()

    # IMPORTANTE: Habilitar claves foráneas
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Tabla pacientes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pacientes (
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
        )
    ''')
    #Tabla citas
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS citas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER NOT NULL,
        fecha DATE NOT NULL,
        hora TIME NOT NULL,
        motivo TEXT,
        estado TEXT DEFAULT 'programada', -- programada, completada, cancelada
        notas TEXT,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
        UNIQUE(fecha, hora)  -- ¡Evita horarios duplicados!
    )
''')
    
    # Tabla historial
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_odontologico (
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
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Base de datos inicializada correctamente")

if __name__ == '__main__':
    init_db()
