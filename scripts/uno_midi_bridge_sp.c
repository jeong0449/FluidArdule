#include <alsa/asoundlib.h>
#include <libserialport.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static volatile sig_atomic_t g_running = 1;
static snd_seq_t *g_seq = NULL;
static int g_out_port = -1;
static struct sp_port *g_port = NULL;

static const char *DEFAULT_SERIAL_PATH =
    "/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_75834353930351211140-if00";

static void handle_sigint(int sig) {
    (void)sig;
    g_running = 0;
}

static void close_serial_port(void) {
    if (g_port) {
        sp_close(g_port);
        sp_free_port(g_port);
        g_port = NULL;
    }
}

static int open_serial_31250(const char *port_name) {
    enum sp_return r;

    close_serial_port();

    r = sp_get_port_by_name(port_name, &g_port);
    if (r != SP_OK || !g_port) {
        fprintf(stderr, "[bridge] sp_get_port_by_name failed for %s\n", port_name);
        g_port = NULL;
        return -1;
    }

    r = sp_open(g_port, SP_MODE_READ);
    if (r != SP_OK) {
        fprintf(stderr, "[bridge] sp_open failed for %s\n", port_name);
        close_serial_port();
        return -1;
    }

    r = sp_set_baudrate(g_port, 31250);
    if (r != SP_OK) {
        fprintf(stderr, "[bridge] sp_set_baudrate(31250) failed\n");
        close_serial_port();
        return -1;
    }

    r = sp_set_bits(g_port, 8);
    if (r != SP_OK) {
        fprintf(stderr, "[bridge] sp_set_bits failed\n");
        close_serial_port();
        return -1;
    }

    r = sp_set_parity(g_port, SP_PARITY_NONE);
    if (r != SP_OK) {
        fprintf(stderr, "[bridge] sp_set_parity failed\n");
        close_serial_port();
        return -1;
    }

    r = sp_set_stopbits(g_port, 1);
    if (r != SP_OK) {
        fprintf(stderr, "[bridge] sp_set_stopbits failed\n");
        close_serial_port();
        return -1;
    }

    r = sp_set_flowcontrol(g_port, SP_FLOWCONTROL_NONE);
    if (r != SP_OK) {
        fprintf(stderr, "[bridge] sp_set_flowcontrol failed\n");
        close_serial_port();
        return -1;
    }

    sp_flush(g_port, SP_BUF_INPUT);
    return 0;
}

static int seq_open_virtual_out(const char *client_name, const char *port_name) {
    int err = snd_seq_open(&g_seq, "default", SND_SEQ_OPEN_OUTPUT, 0);
    if (err < 0) {
        fprintf(stderr, "snd_seq_open: %s\n", snd_strerror(err));
        return -1;
    }

    snd_seq_set_client_name(g_seq, client_name);

    g_out_port = snd_seq_create_simple_port(
        g_seq,
        port_name,
        SND_SEQ_PORT_CAP_READ | SND_SEQ_PORT_CAP_SUBS_READ,
        SND_SEQ_PORT_TYPE_MIDI_GENERIC | SND_SEQ_PORT_TYPE_APPLICATION);

    if (g_out_port < 0) {
        fprintf(stderr, "snd_seq_create_simple_port: %s\n", snd_strerror(g_out_port));
        snd_seq_close(g_seq);
        g_seq = NULL;
        return -1;
    }

    return 0;
}

static void send_cc(int ch, int cc, int val) {
    snd_seq_event_t ev;
    snd_seq_ev_clear(&ev);
    snd_seq_ev_set_source(&ev, g_out_port);
    snd_seq_ev_set_subs(&ev);
    snd_seq_ev_set_direct(&ev);
    snd_seq_ev_set_controller(&ev, ch, cc, val);
    snd_seq_event_output_direct(g_seq, &ev);
}

static void send_panic_all_channels(void) {
    if (!g_seq || g_out_port < 0) {
        return;
    }

    for (int ch = 0; ch < 16; ++ch) {
        send_cc(ch, 64, 0);   // Sustain Off
        send_cc(ch, 123, 0);  // All Notes Off
        send_cc(ch, 120, 0);  // All Sound Off
    }
}

static void normalize_event(snd_seq_event_t *ev) {
    if (!ev) return;

    if (ev->type == SND_SEQ_EVENT_NOTEON && ev->data.note.velocity == 0) {
        ev->type = SND_SEQ_EVENT_NOTEOFF;
    }
}

int main(int argc, char *argv[]) {
    const char *serial_path = DEFAULT_SERIAL_PATH;
    const char *client_name = "UNO-bridge";
    const char *port_name = "UNO-serial-in";

    if (argc >= 2) {
        serial_path = argv[1];
    }

    signal(SIGINT, handle_sigint);
    signal(SIGTERM, handle_sigint);

    if (seq_open_virtual_out(client_name, port_name) < 0) {
        return 1;
    }

    snd_midi_event_t *parser = NULL;
    int err = snd_midi_event_new(1024, &parser);
    if (err < 0) {
        fprintf(stderr, "snd_midi_event_new: %s\n", snd_strerror(err));
        snd_seq_close(g_seq);
        return 1;
    }

    // 입력 파서에서 running status 허용
    snd_midi_event_no_status(parser, 0);
    snd_midi_event_reset_encode(parser);

    fprintf(stderr, "[bridge] started\n");
    fprintf(stderr, "[bridge] serial target: %s\n", serial_path);
    fprintf(stderr, "[bridge] ALSA client: %s / port: %s\n", client_name, port_name);
    fprintf(stderr, "[bridge] waiting for serial device...\n");

    int serial_connected = 0;
    int timeout_count = 0;
    const int TIMEOUT_LIMIT = 20;  // 100ms * 20 = 약 2초

    while (g_running) {
        if (!serial_connected) {
            if (open_serial_31250(serial_path) == 0) {
                serial_connected = 1;
                timeout_count = 0;
                snd_midi_event_reset_encode(parser);
                sp_flush(g_port, SP_BUF_INPUT);

                // UNO auto-reset 안정화 대기
                usleep(2000 * 1000);

                fprintf(stderr, "[bridge] serial connected\n");
            } else {
                sleep(1);
                continue;
            }
        }

        unsigned char byte = 0;
        int n = sp_blocking_read(g_port, &byte, 1, 100);

        if (n < 0) {
            fprintf(stderr, "[bridge] serial read error -> reconnecting\n");
            close_serial_port();
            serial_connected = 0;
            timeout_count = 0;
            snd_midi_event_reset_encode(parser);
            usleep(300 * 1000);
            continue;
        }

        if (n == 0) {
            timeout_count++;

            if (timeout_count >= TIMEOUT_LIMIT) {
                if (access(serial_path, F_OK) != 0) {
                    fprintf(stderr, "[bridge] serial device disappeared -> reconnecting\n");
                    close_serial_port();
                    serial_connected = 0;
                    timeout_count = 0;
                    snd_midi_event_reset_encode(parser);
                    usleep(300 * 1000);
                    continue;
                }
                timeout_count = 0;
            }

            continue;
        }

        timeout_count = 0;

        snd_seq_event_t ev;
        snd_seq_ev_clear(&ev);

        int rc = snd_midi_event_encode_byte(parser, byte, &ev);
        if (rc < 0) {
            snd_midi_event_reset_encode(parser);
            continue;
        }

        if (rc == 1) {
            normalize_event(&ev);
            snd_seq_ev_set_source(&ev, g_out_port);
            snd_seq_ev_set_subs(&ev);
            snd_seq_ev_set_direct(&ev);

            int out_rc = snd_seq_event_output_direct(g_seq, &ev);
            if (out_rc < 0) {
                fprintf(stderr, "[bridge] snd_seq_event_output_direct: %s\n",
                        snd_strerror(out_rc));
            }
        }
    }

    fprintf(stderr, "[bridge] stopping...\n");

    send_panic_all_channels();

    snd_midi_event_free(parser);

    if (g_seq) {
        snd_seq_close(g_seq);
        g_seq = NULL;
    }

    close_serial_port();

    fprintf(stderr, "[bridge] stopped\n");
    return 0;
}
