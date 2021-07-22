# Introduction

`baremetal-report` and `baremetal-report.service` are example tools
that you can use inside your image under test. They will report
progress status back to `baremetal_run.py`. Most importantly they can
signal when the test is complete to avoid always having to wait until
the test timeouts.
