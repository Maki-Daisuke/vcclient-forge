package main

import (
	"net"
	"testing"
	"time"
)

func TestParseRemoteAddr(t *testing.T) {
	tests := []struct {
		name string
		args []string
		want string
	}{
		{
			name: "no remote flag",
			args: []string{"--other", "flag"},
			want: "",
		},
		{
			name: "remote flag with space and port",
			args: []string{"--remote", "192.168.1.100:18888"},
			want: "192.168.1.100:18888",
		},
		{
			name: "remote flag with space without port",
			args: []string{"--remote", "192.168.1.100"},
			want: "192.168.1.100:18888",
		},
		{
			name: "remote flag with equal sign",
			args: []string{"--remote=example.com:8080"},
			want: "example.com:8080",
		},
		{
			name: "remote flag with equal sign without port",
			args: []string{"--remote=example.com"},
			want: "example.com:18888",
		},
		{
			name: "remote flag at end of args without value",
			args: []string{"--remote"},
			want: "",
		},
		{
			name: "short flag -r with space and port",
			args: []string{"-r", "10.0.0.1:9999"},
			want: "10.0.0.1:9999",
		},
		{
			name: "short flag -r with unknown flags mixed",
			args: []string{"--devtools", "-r", "10.0.0.1", "--some-other-arg=123"},
			want: "10.0.0.1:18888",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := parseRemoteAddr(tt.args)
			if got != tt.want {
				t.Errorf("parseRemoteAddr(%v) = %q; want %q", tt.args, got, tt.want)
			}
		})
	}
}

func TestProxyConnection(t *testing.T) {
	// 1. Create a mock remote server that echoes with prefix
	remoteLn, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen on mock remote: %v", err)
	}
	defer remoteLn.Close()

	remoteAddr := remoteLn.Addr().String()

	go func() {
		for {
			conn, err := remoteLn.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer c.Close()
				buf := make([]byte, 1024)
				n, err := c.Read(buf)
				if err != nil {
					return
				}
				_, _ = c.Write(append([]byte("ECHO:"), buf[:n]...))
			}(conn)
		}
	}()

	// 2. Start a mock proxy listener
	proxyLn, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen on mock proxy: %v", err)
	}
	defer proxyLn.Close()

	go func() {
		for {
			conn, err := proxyLn.Accept()
			if err != nil {
				return
			}
			go proxyConnection(conn, remoteAddr)
		}
	}()

	// 3. Connect to proxy and verify communication
	client, err := net.DialTimeout("tcp", proxyLn.Addr().String(), 2*time.Second)
	if err != nil {
		t.Fatalf("failed to dial proxy: %v", err)
	}
	defer client.Close()

	msg := []byte("hello-forge")
	if _, err := client.Write(msg); err != nil {
		t.Fatalf("failed to write to proxy: %v", err)
	}

	res := make([]byte, 1024)
	n, err := client.Read(res)
	if err != nil {
		t.Fatalf("failed to read from proxy: %v", err)
	}

	expected := "ECHO:hello-forge"
	if string(res[:n]) != expected {
		t.Fatalf("expected response %q, got %q", expected, string(res[:n]))
	}
}
