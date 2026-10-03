HELM ?= helm

deploy:
	$(HELM) upgrade --install app ./chart --atomic --force
	$(HELM) status app --show-resources
	$(HELM) repo update --fail-on-repo-update-fail
