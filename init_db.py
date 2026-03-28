import sqlite3

def init_db():
    conn = sqlite3.connect('consultorio_dental.db')
    cursor = conn.cursor()
    
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
        FOREIGN KEY (paciente_id) REFERENCES pacientes(id),
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
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
        )
    ''')
    
    # Insertar datos de prueba
    cursor.execute('''
        INSERT OR IGNORE INTO pacientes (id, nombre_completo, dni, telefono, alergias)
        VALUES 
        (1, 'Juan Pérez García', '12345678', '555-0101', 'Alergia a la penicilina'),
        (2, 'María Rodríguez López', '87654321', '555-0202', 'Ninguna'),
        (3, 'Carlos Martínez Sánchez', '45678912', '555-0303', 'Diabetes tipo 2')
    ''')
    
    cursor.execute('''
        INSERT OR IGNORE INTO historial_odontologico 
        (paciente_id, fecha_consulta, procedimiento, diagnostico, tratamiento_realizado)
        VALUES 
        (1, '2024-01-15', 'Limpieza dental', 'Tartaro moderado', 'Profilaxis completa'),
        (1, '2024-02-20', 'Empaste', 'Caries en molar superior', 'Resina compuesta'),
        (2, '2024-03-10', 'Extracción', 'Tercer molar impactado', 'Extracción quirúrgica')
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Base de datos creada exitosamente")

if __name__ == '__main__':
    init_db()