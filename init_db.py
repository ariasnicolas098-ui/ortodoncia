"""
init_db.py - Script para inicializar la base de datos manualmente
"""
from database import db

def init_db():
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Tipo de PRIMARY KEY según la base de datos
    if db.is_postgres:
        pk_type = "SERIAL PRIMARY KEY"
        print("🐘 Inicializando PostgreSQL...")
    else:
        pk_type = "INTEGER PRIMARY KEY AUTOINCREMENT"
        print("🗄️ Inicializando SQLite...")
    
    # Tabla pacientes
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS pacientes (
            id {pk_type},
            nombre_completo TEXT NOT NULL,
            dni TEXT UNIQUE,
            fecha_nacimiento DATE,
            telefono TEXT,
            email TEXT,
            direccion TEXT,
            alergias TEXT DEFAULT 'Ninguna',
            medicamentos_actuales TEXT DEFAULT 'Ninguno',
            condiciones_medicas TEXT DEFAULT 'Ninguna',
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabla historial
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS historial_odontologico (
            id {pk_type},
            paciente_id INTEGER REFERENCES pacientes(id) ON DELETE CASCADE,
            fecha_consulta DATE,
            hora_consulta TIME,
            motivo_consulta TEXT,
            diagnostico TEXT,
            tratamiento_realizado TEXT,
            dientes_tratados TEXT,
            procedimiento TEXT,
            observaciones TEXT,
            odontologo TEXT
        )
    ''')
    
    # Tabla citas
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS citas (
            id {pk_type},
            paciente_id INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
            fecha DATE NOT NULL,
            hora TIME NOT NULL,
            motivo TEXT,
            estado TEXT DEFAULT 'programada',
            notas TEXT,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fecha, hora)
        )
    ''')
    
    # Tabla archivos
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS archivos (
            id {pk_type},
            paciente_id INTEGER REFERENCES pacientes(id) ON DELETE CASCADE,
            nombre TEXT NOT NULL,
            tipo TEXT,
            descripcion TEXT,
            ruta TEXT NOT NULL,
            fecha_subida TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tablas WhatsApp
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS whatsapp_mensajes (
            id {pk_type},
            numero TEXT NOT NULL,
            mensaje TEXT,
            tipo TEXT DEFAULT 'recibido',
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            procesado INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS whatsapp_sesiones (
            id {pk_type},
            numero TEXT UNIQUE,
            paciente_id INTEGER REFERENCES pacientes(id),
            estado TEXT DEFAULT 'nuevo',
            ultimo_mensaje TIMESTAMP,
            datos_conversacion TEXT
        )
    ''')
    
    # Tablas de abonos
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS condiciones (
            id {pk_type},
            nombre TEXT NOT NULL UNIQUE,
            precio REAL NOT NULL,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS abonos (
            id {pk_type},
            paciente_id INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
            condicion_id INTEGER NOT NULL REFERENCES condiciones(id),
            precio_total REAL NOT NULL,
            total_abonado REAL DEFAULT 0,
            estado TEXT DEFAULT 'pendiente',
            notas TEXT,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS pagos (
            id {pk_type},
            abono_id INTEGER NOT NULL REFERENCES abonos(id) ON DELETE CASCADE,
            monto REAL NOT NULL,
            fecha_pago TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Base de datos inicializada correctamente")

if __name__ == '__main__':
    init_db()
