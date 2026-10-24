package main

import (
	"strings"
	"testing"
)

func TestReadySentinelDetection(t *testing.T) {
	output := "Some initial log output\n" + READY_SENTINEL + "\nmore logs"
	if !strings.Contains(output, READY_SENTINEL) {
		t.Errorf("expected READY_SENTINEL to be detected in output")
	}
}

func TestResolveBackendCommand(t *testing.T) {
	bin, args, dir, err := resolveBackendCommand()
	if err != nil {
		t.Fatalf("resolveBackendCommand failed: %v", err)
	}
	if bin == "" {
		t.Errorf("expected non-empty binary path")
	}
	if len(args) == 0 {
		t.Errorf("expected non-empty args")
	}
	if dir == "" {
		t.Errorf("expected non-empty directory")
	}
}
