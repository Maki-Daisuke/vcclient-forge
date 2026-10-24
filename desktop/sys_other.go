//go:build !windows

package main

import (
	"context"
	"os"
	"os/exec"
	"time"
)

// createCommand is just a alias for exec.Command on non-Windows platforms.
func createCommand(binPath string, args ...string) *exec.Cmd {
	return exec.Command(binPath, args...)
}

// stopProcess terminates the process and all child processes created by it.
func stopProcess(cmd *exec.Cmd) error {
	if cmd == nil || cmd.Process == nil {
		return nil
	}

	if err := cmd.Process.Signal(os.Interrupt); err != nil {
		return err
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	waitDone := make(chan error, 1)
	go func() {
		waitDone <- cmd.Wait()
	}()

	select {
	case err := <-waitDone:
		return err

	case <-ctx.Done():
		if err := cmd.Process.Kill(); err != nil {
			return err
		}
		err := <-waitDone
		return err
	}
}
