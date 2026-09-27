.PHONY: test demo api web

export PYTHONPATH := backend/src:backend:.pydeps

test:
	python3 -m pytest backend/tests

demo:
	python3 -m agentgate.cli demo

api:
	python3 -m agentgate.cli serve

web:
	cd frontend && npm run dev
