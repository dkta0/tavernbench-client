package main

import (
	"flag"
	"fmt"
	"net/url"
	"os"

	"github.com/tavernbench/cli/internal/httpapi"
)

func leaderboardCmd(args []string) {
	fs := flag.NewFlagSet("leaderboard", flag.ExitOnError)
	scenario := fs.String("scenario", "", "Scenario id")
	fs.Parse(args)
	if *scenario == "" {
		fmt.Fprintln(os.Stderr, "usage: tavernbench leaderboard --scenario X")
		os.Exit(2)
	}
	body, err := httpapi.Get("/api/leaderboard?scenario=" + url.QueryEscape(*scenario))
	if err != nil {
		die(err)
	}
	fmt.Println(string(body))
}
