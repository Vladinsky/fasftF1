from flask import Flask, render_template
from flask_socketio import SocketIO
import numpy as np
from io import BytesIO
import base64
import threading
import time
import fastf1
import matplotlib
matplotlib.use('Agg')  # Imposta matplotlib in modalità non interattiva
import matplotlib.pyplot as plt

app = Flask(__name__)
socketio = SocketIO(app)

# Carica i dati della sessione
session = fastf1.get_session(2023, 'Monza', 'Q')  # Cambia con l'anno e il circuito desiderato
session.load()
print("Sessione caricata correttamente.")

# Ottieni il giro più veloce
lap = session.laps.pick_fastest()
pos = lap.get_pos_data()
circuit_info = session.get_circuit_info()
print("Dati del giro più veloce caricati.")

# Funzione per ruotare le coordinate
def rotate(xy, *, angle):
    rot_mat = np.array([[np.cos(angle), np.sin(angle)],
                       [-np.sin(angle), np.cos(angle)]])
    return np.matmul(xy, rot_mat)

# Ottieni le coordinate del tracciato
track = pos.loc[:, ('X', 'Y')].to_numpy()
track_angle = circuit_info.rotation / 180 * np.pi
rotated_track = rotate(track, angle=track_angle)
print("Coordinate del tracciato elaborate.")

# Ottieni i dati di telemetria
telemetry = lap.get_telemetry()
distance = telemetry['Distance'].to_numpy()  # Converti in array NumPy
throttle = telemetry['Throttle'].to_numpy()  # Converti in array NumPy
brake = telemetry['Brake'].to_numpy()  # Converti in array NumPy
speed = telemetry['Speed'].to_numpy()  # Converti in array NumPy
print("Dati di telemetria caricati.")

# Verifica i dati
print("Distanza:", distance)
print("Accelerazione:", throttle)
print("Frenata:", brake)
print("Velocità:", speed)
print("Lunghezza distanza:", len(distance))
print("Lunghezza accelerazione:", len(throttle))
print("Lunghezza frenata:", len(brake))
print("Lunghezza velocità:", len(speed))

# Variabile globale per la posizione corrente
current_index = 0

# Funzione per creare il grafico dello stile di guida
def create_telemetry_plot(index):
    plt.style.use('dark_background')  # Sfondo nero
    fig, ax = plt.subplots(figsize=(10, 5))

    # Grafico dell'accelerazione
    ax.plot(distance, throttle, color='green', label='Accelerazione (%)', linewidth=2)

    # Grafico della frenata
    ax.plot(distance, brake, color='red', label='Frenata (%)', linewidth=2)

    # Grafico della velocità (sull'asse secondario)
    ax2 = ax.twinx()
    ax2.plot(distance, speed, color='white', label='Velocità (km/h)', linewidth=2)
    ax2.set_ylabel('Velocità (km/h)', color='white')
    ax2.tick_params(axis='y', labelcolor='white')

    # Punto corrente sul grafico
    ax.plot(distance[index], throttle[index], 'ro', markersize=10, label='Posizione corrente')
    ax2.plot(distance[index], speed[index], 'ro', markersize=10)

    # Formattazione del grafico
    ax.set_xlabel('Distanza (m)', color='white')
    ax.set_ylabel('Accelerazione/Frenata (%)', color='white')
    ax.tick_params(axis='x', colors='white')
    ax.tick_params(axis='y', colors='white')
    plt.title(f"Stile di Guida - {lap['Driver']} (Giro {lap['LapNumber']})", pad=20, color='white')
    fig.legend(loc='upper right', bbox_to_anchor=(0.9, 0.9))

    # Converti il grafico in un'immagine base64
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', transparent=True)
    buf.seek(0)
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close()
    return image_base64

# Funzione per creare il grafico del tracciato
def create_track_plot(index):
    plt.style.use('dark_background')  # Sfondo nero
    fig, ax = plt.subplots(figsize=(10, 5))

    # Disegna il tracciato
    ax.plot(rotated_track[:, 0], rotated_track[:, 1], color='white', linewidth=2, label='Tracciato')

    # Aggiungi i corner
    offset_vector = [500, 0]  # offset length is chosen arbitrarily to 'look good'
    for _, corner in circuit_info.corners.iterrows():
        txt = f"{corner['Number']}{corner['Letter']}"
        offset_angle = corner['Angle'] / 180 * np.pi
        offset_x, offset_y = rotate(offset_vector, angle=offset_angle)
        text_x = corner['X'] + offset_x
        text_y = corner['Y'] + offset_y
        text_x, text_y = rotate([text_x, text_y], angle=track_angle)
        track_x, track_y = rotate([corner['X'], corner['Y']], angle=track_angle)
        ax.scatter(text_x, text_y, color='grey', s=140)
        ax.plot([track_x, text_x], [track_y, text_y], color='grey')
        ax.text(text_x, text_y, txt, va='center_baseline', ha='center', size='small', color='white')

    # Aggiungi il punto rosso per la posizione corrente
    ax.plot(rotated_track[index, 0], rotated_track[index, 1], 'ro', markersize=10, label='Posizione corrente')

    # Formattazione del grafico
    ax.set_title(session.event['Location'], color='white')
    ax.axis('equal')
    ax.set_xticks([])  # Nascondi i tick dell'asse x
    ax.set_yticks([])  # Nascondi i tick dell'asse y
    ax.legend(loc='upper right')

    # Converti il grafico in un'immagine base64
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', transparent=True)
    buf.seek(0)
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close()
    return image_base64

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    def send_updates():
        global current_index
        while True:
            # Invia i grafici aggiornati
            telemetry_image = create_telemetry_plot(current_index)
            track_image = create_track_plot(current_index)
            socketio.emit('update', {
                'telemetry_image': telemetry_image,
                'track_image': track_image,
                'index': current_index,
                'max_index': len(distance) - 1
            })
            current_index = (current_index + 1) % len(distance)  # Avanza al prossimo punto
            time.sleep(0.5)  # Aggiorna ogni 0.5 secondi

    threading.Thread(target=send_updates).start()

@socketio.on('set_position')
def handle_set_position(data):
    global current_index
    current_index = int(data['index'])
    telemetry_image = create_telemetry_plot(current_index)
    track_image = create_track_plot(current_index)
    socketio.emit('update', {
        'telemetry_image': telemetry_image,
        'track_image': track_image,
        'index': current_index,
        'max_index': len(distance) - 1
    })

if __name__ == '__main__':
    socketio.run(app, debug=False)