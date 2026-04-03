# Changelog

## [0.6.0](https://github.com/velocitylabo/tobira/compare/tobira-python-v0.5.0...tobira-python-v0.6.0) (2026-04-01)


### Features

* add package keywords for npm/PyPI discoverability ([#104](https://github.com/velocitylabo/tobira/issues/104)) ([8d90682](https://github.com/velocitylabo/tobira/commit/8d9068290a40f1afe703c5403c174f52a3df9f58))
* **core:** add GGUF export pipeline for Ollama deployment ([#149](https://github.com/velocitylabo/tobira/issues/149)) ([ac59b83](https://github.com/velocitylabo/tobira/commit/ac59b83f09ca54102bd806e75f575c0906608139))
* **explainability:** add attention-based token attribution to /predict ([#119](https://github.com/velocitylabo/tobira/issues/119)) ([bd25f40](https://github.com/velocitylabo/tobira/commit/bd25f40ca62af7b0500765bccd3c72045b3cf7bf))
* **monitoring:** add OpenTelemetry / Prometheus metrics export ([#150](https://github.com/velocitylabo/tobira/issues/150)) ([a2d4c0f](https://github.com/velocitylabo/tobira/commit/a2d4c0f7f4c2324d588111f06756ffd393521a19))
* **serving:** add multi-tenant management and tenant isolation ([#151](https://github.com/velocitylabo/tobira/issues/151)) ([e220118](https://github.com/velocitylabo/tobira/commit/e2201185d232fb0e958575ecd0f6add7b47592e9))
* **serving:** add RBAC and audit logging ([#152](https://github.com/velocitylabo/tobira/issues/152)) ([224c5d1](https://github.com/velocitylabo/tobira/commit/224c5d1dfb28e9d55679ff5a284f6874888c7e22))
* **tracing:** add OpenTelemetry tracing, structured logging, and Grafana dashboards ([#153](https://github.com/velocitylabo/tobira/issues/153)) ([a32088a](https://github.com/velocitylabo/tobira/commit/a32088a3d3db61d5175b4d570edcbbf4840ee4e3))


### Documentation

* rewrite README for PyPI and npm ([45ac6fd](https://github.com/velocitylabo/tobira/commit/45ac6fd4692f15e14b5ae0a7fed7b7eb08016650))


### Miscellaneous

* migrate GitHub org from piroz to velocitylabo ([#89](https://github.com/velocitylabo/tobira/issues/89)) ([f63e46e](https://github.com/velocitylabo/tobira/commit/f63e46ec9f57f6251ceb076091754d8e99045e57))

## [0.5.0](https://github.com/velocitylabo/tobira/compare/tobira-python-v0.4.0...tobira-python-v0.5.0) (2026-03-21)


### Features

* **backends:** add few-shot prompting support for LLM backends ([#105](https://github.com/velocitylabo/tobira/issues/105)) ([43c7db5](https://github.com/velocitylabo/tobira/commit/43c7db5ff962e073aeb0355d6b90fafb05545af2))
* **cli:** add auxiliary config validation to doctor command ([#113](https://github.com/velocitylabo/tobira/issues/113)) ([193ae1a](https://github.com/velocitylabo/tobira/commit/193ae1adf77b9138612c8d1a0db25c907d0a4793))
* **cli:** add feature configuration checks to doctor command ([#112](https://github.com/velocitylabo/tobira/issues/112)) ([9ab68c6](https://github.com/velocitylabo/tobira/commit/9ab68c66292758f964454595e0556967541749e6))
* **cli:** add infrastructure checks to doctor command ([#110](https://github.com/velocitylabo/tobira/issues/110)) ([1b276d2](https://github.com/velocitylabo/tobira/commit/1b276d26b8ee9b10c7918e4e0dbf25ebd2ff111a))
* **models:** recommend DeBERTa-v3 as preferred base model ([#106](https://github.com/velocitylabo/tobira/issues/106)) ([f2073db](https://github.com/velocitylabo/tobira/commit/f2073dbfcc262cf7f680c763adaf66f4692d9e51))


### Tests

* **cli:** add tests for doctor auxiliary config validation checks ([#114](https://github.com/velocitylabo/tobira/issues/114)) ([7068427](https://github.com/velocitylabo/tobira/commit/70684273b90a82bae787e5704521ff8c0c9e19c0))

## [0.4.0](https://github.com/velocitylabo/tobira/compare/tobira-python-v0.3.0...tobira-python-v0.4.0) (2026-03-20)


### Features

* **metrics:** redefine success metrics with local telemetry ([#102](https://github.com/velocitylabo/tobira/issues/102)) ([0ca9929](https://github.com/velocitylabo/tobira/commit/0ca9929283ef85a319889166b04b10476ba1dfc1))
* **serving:** add Bearer token API key authentication ([#100](https://github.com/velocitylabo/tobira/issues/100)) ([cf4944d](https://github.com/velocitylabo/tobira/commit/cf4944de91632234fcacccf457aa049482d8e39e))


### Miscellaneous

* **serving:** error message design guidelines and improvements ([#101](https://github.com/velocitylabo/tobira/issues/101)) ([89e73d3](https://github.com/velocitylabo/tobira/commit/89e73d3cda9b8134333470b02fdc86ed15ad277b))

## [0.3.0](https://github.com/velocitylabo/tobira/compare/tobira-python-v0.2.0...tobira-python-v0.3.0) (2026-03-18)


### Features

* **backends:** add entry_points plugin architecture for custom backends ([#87](https://github.com/velocitylabo/tobira/issues/87)) ([a262e77](https://github.com/velocitylabo/tobira/commit/a262e771a1cc73c6087c6a381029273873297a46))
* **cli:** add tobira demo command for Docker Compose demo environment ([#79](https://github.com/velocitylabo/tobira/issues/79)) ([fda311f](https://github.com/velocitylabo/tobira/commit/fda311f5e25f08e5d1f41904fe712a2d1afbaf42))
* **cli:** add tobira train command ([#78](https://github.com/velocitylabo/tobira/issues/78)) ([769e1bc](https://github.com/velocitylabo/tobira/commit/769e1bcda0738dff675870e1c2d84a19cb48e5bf))
* **core:** add fine-tuning pipeline (trainer.py) ([#77](https://github.com/velocitylabo/tobira/issues/77)) ([fe0b566](https://github.com/velocitylabo/tobira/commit/fe0b5660a7836b4d9fb7b177bfbac3ad07a1d449))
* **deploy:** add high-availability support ([#91](https://github.com/velocitylabo/tobira/issues/91)) ([d2c4ee0](https://github.com/velocitylabo/tobira/commit/d2c4ee0b5238de444e131bfe2b6a9bbbfa163c80))
* **evaluation:** add Active Learning module for uncertainty sampling ([#84](https://github.com/velocitylabo/tobira/issues/84)) ([438113f](https://github.com/velocitylabo/tobira/commit/438113ff953fa8c7198c3e62f8eca290a0c3023a))
* **monitoring:** add notification integration (Slack / Teams / email) ([#86](https://github.com/velocitylabo/tobira/issues/86)) ([6079cb3](https://github.com/velocitylabo/tobira/commit/6079cb3a63a2382185ac2c6466e77af97c84f9b8))
* **monitoring:** add pluggable store abstraction for external backends ([#85](https://github.com/velocitylabo/tobira/issues/85)) ([46a54a1](https://github.com/velocitylabo/tobira/commit/46a54a1123255c611a58de880236e0a8db5663c7))
* **preprocessing:** add Japanese PII recognizer ([#76](https://github.com/velocitylabo/tobira/issues/76)) ([8d8af90](https://github.com/velocitylabo/tobira/commit/8d8af90f9ec6464be882812314bd51cc5fdba778))
* **preprocessing:** add preprocessing pipeline integration ([#75](https://github.com/velocitylabo/tobira/issues/75)) ([dab2847](https://github.com/velocitylabo/tobira/commit/dab28474f302108ccc437128e49e6deebc81b449))
* **serving:** A/B test support for model comparison ([#89](https://github.com/velocitylabo/tobira/issues/89)) ([92e712a](https://github.com/velocitylabo/tobira/commit/92e712afcf9cb0352e3d09799b00933f40affbe0))
* **serving:** add API versioning with /v1/ prefix ([#92](https://github.com/velocitylabo/tobira/issues/92)) ([f21d0b0](https://github.com/velocitylabo/tobira/commit/f21d0b01dbc2d52207ea78b05e39e71d7670e4c8))
* **serving:** add feedback UI to dashboard with one-click reporting ([#83](https://github.com/velocitylabo/tobira/issues/83)) ([92ac971](https://github.com/velocitylabo/tobira/commit/92ac9715cdee768380daea0495b2e1c4e87cb188))
* **serving:** refresh dashboard UX with traffic-light status and Chart.js ([#82](https://github.com/velocitylabo/tobira/issues/82)) ([6078b92](https://github.com/velocitylabo/tobira/commit/6078b929744afe7a9558e2053cef5ef660ff6c09))

## [0.2.0](https://github.com/velocitylabo/tobira/compare/tobira-python-v0.1.0...tobira-python-v0.2.0) (2026-03-16)


### Features

* **adversarial:** add AI-generated text detection ([#64](https://github.com/velocitylabo/tobira/issues/64)) ([2b3c867](https://github.com/velocitylabo/tobira/commit/2b3c8675233422d3c4292ce65f51a2c6be087e4d))
* **backends:** add header-based classification ([#65](https://github.com/velocitylabo/tobira/issues/65)) ([0fa9573](https://github.com/velocitylabo/tobira/commit/0fa95730e710453aa7628449a93a9085bbbe12bd))
* **cli:** add tobira monitor --watch daemon mode ([#61](https://github.com/velocitylabo/tobira/issues/61)) ([4a41e84](https://github.com/velocitylabo/tobira/commit/4a41e84d90fc4bb587dd43047155a4c4d7590a48))
* **core:** add knowledge distillation pipeline ([#68](https://github.com/velocitylabo/tobira/issues/68)) ([c6d4d5b](https://github.com/velocitylabo/tobira/commit/c6d4d5b8c552aef841e1b3af3233a97285f108e6))
* **integrations:** add Postfix milter integration ([#66](https://github.com/velocitylabo/tobira/issues/66)) ([16029b9](https://github.com/velocitylabo/tobira/commit/16029b969447dbb33e7989059d06925acf252b5f))
* **monitoring:** add automatic retrain trigger ([#62](https://github.com/velocitylabo/tobira/issues/62)) ([724ce01](https://github.com/velocitylabo/tobira/commit/724ce011eeaa05ec5139bd398a741510ad7a3b70))
* **monitoring:** add phase transition advisor ([#63](https://github.com/velocitylabo/tobira/issues/63)) ([ef3a53a](https://github.com/velocitylabo/tobira/commit/ef3a53a4fa74ee4f507c4b679904b65968acbd0a))
* **serving:** add web dashboard for monitoring and statistics ([#67](https://github.com/velocitylabo/tobira/issues/67)) ([cd85e7b](https://github.com/velocitylabo/tobira/commit/cd85e7bbe52e98e69f2bb5cdd1c1dacd187e8596))


### Bug Fixes

* **backends:** patch NumPy 2.x compat for fasttext predict ([#60](https://github.com/velocitylabo/tobira/issues/60)) ([3a3a2e8](https://github.com/velocitylabo/tobira/commit/3a3a2e8d1edf397c18ef9248246eb341190495c1))

## [0.1.0](https://github.com/velocitylabo/tobira/compare/tobira-python-v0.0.1...tobira-python-v0.1.0) (2026-03-15)


### Features

* **adversarial:** add homoglyph and invisible Unicode detectors ([#49](https://github.com/velocitylabo/tobira/issues/49)) ([04116e6](https://github.com/velocitylabo/tobira/commit/04116e6fa8c6e53944f93420e5118edd035e0881))
* **backends:** add BackendProtocol and FastTextBackend implementation ([b54d87d](https://github.com/velocitylabo/tobira/commit/b54d87d1c93db6400350291d459d33ea3a02348f)), closes [#3](https://github.com/velocitylabo/tobira/issues/3)
* **backends:** add BertBackend implementation ([1a10267](https://github.com/velocitylabo/tobira/commit/1a10267fd0b2ff1cbb57ec943b804c2b0a6e57cb))
* **backends:** add ensemble backend ([65c9c5b](https://github.com/velocitylabo/tobira/commit/65c9c5b62b6ad0bb277e4bb3fe58e85d71cad50e))
* **backends:** add multiclass spam classification (8 subcategories) ([#55](https://github.com/velocitylabo/tobira/issues/55)) ([abbe6ff](https://github.com/velocitylabo/tobira/commit/abbe6ffa917235a051c3fd76c1badaa00ad9503c))
* **backends:** add Ollama and OpenAI-compatible LLM API backends ([8f93597](https://github.com/velocitylabo/tobira/commit/8f93597074d32e54d4889472cef85c4e950a1788))
* **backends:** add ONNX export and OnnxBackend ([6931db0](https://github.com/velocitylabo/tobira/commit/6931db0a8bd9cf4604685af9dacad66cc4970a9e))
* **backends:** add TwoStageBackend for two-stage filtering ([3af957d](https://github.com/velocitylabo/tobira/commit/3af957de99cbef67785ddb57dfe54b606f08811b))
* **cli:** add CLI framework with tobira serve subcommand ([bad1eb7](https://github.com/velocitylabo/tobira/commit/bad1eb7f1b2e9e00ceffb03d00845b46233aa141))
* **cli:** add tobira doctor subcommand ([d814dcb](https://github.com/velocitylabo/tobira/commit/d814dcbac8deb2a2bdcde221baeec89eeb39dc35))
* **cli:** add tobira evaluate subcommand  ([add9efb](https://github.com/velocitylabo/tobira/commit/add9efb91151fc16bf3cea56c0dbe7ce9fb1a1aa))
* **cli:** add tobira init subcommand ([ef3980d](https://github.com/velocitylabo/tobira/commit/ef3980d3ce3e432fd4e40aa6071fbb7d34136115))
* **cli:** add tobira monitor subcommand ([4c1c812](https://github.com/velocitylabo/tobira/commit/4c1c812fa3003188f899eaf7fd4bbdd949d7ae6e))
* **evaluation:** add benchmark suite for backend comparison ([#54](https://github.com/velocitylabo/tobira/issues/54)) ([3f6fa0a](https://github.com/velocitylabo/tobira/commit/3f6fa0a8992c79bd6e5d3ec08d03759bdde198ac))
* **evaluation:** add evaluation module ([5866562](https://github.com/velocitylabo/tobira/commit/5866562aa4734e3667a97227baf77756e7da63cd))
* **hub:** add HuggingFace Hub model upload and download support ([#53](https://github.com/velocitylabo/tobira/issues/53)) ([9848acb](https://github.com/velocitylabo/tobira/commit/9848acb17d1a9d2875a565ef94bbb604cac0ec01))
* **monitoring:** add concept drift detection with Redis statistics ([#50](https://github.com/velocitylabo/tobira/issues/50)) ([d7c9e8f](https://github.com/velocitylabo/tobira/commit/d7c9e8f27954ba0c855447aba55f18ba5ea0ac45))
* **monitoring:** add prediction metrics logging middleware ([5dac908](https://github.com/velocitylabo/tobira/commit/5dac908c63534e490504200e97bca729fe47cd27))
* **multilingual:** add language detection and multilingual support ([#52](https://github.com/velocitylabo/tobira/issues/52)) ([83e8143](https://github.com/velocitylabo/tobira/commit/83e814349befca4ebc885c25c087c77a6164ada2))
* **pipeline:** add feedback loop endpoint and JSONL store ([#51](https://github.com/velocitylabo/tobira/issues/51)) ([f44ae3b](https://github.com/velocitylabo/tobira/commit/f44ae3baf371dff8f2ff0c30ed5fd2eef2b57449))
* **preprocessing,data:** add PII anonymization and synthetic data generation ([4637443](https://github.com/velocitylabo/tobira/commit/46374434e7e34e002b2f244852cabf286325c0c7))
* **serving:** add FastAPI server with POST /predict and GET /health ([bcc4a9b](https://github.com/velocitylabo/tobira/commit/bcc4a9b0014295f618df2c363716747ef97700af))
* **serving:** add request size limit and OpenAPI schema improvements ([b681157](https://github.com/velocitylabo/tobira/commit/b6811578ed25b4b9d3bdc0a1069621b1b23f3800))


### Bug Fixes

* **backends:** select highest-score label in FastTextBackend.predict() ([4154cfc](https://github.com/velocitylabo/tobira/commit/4154cfc4892481f02ad6770d6355c56a71b9c3a4))


### Code Refactoring

* **backends:** make backend deps optional and improve error handling ([6879566](https://github.com/velocitylabo/tobira/commit/6879566664acad71058527229df6cf9730738931))


### Tests

* **python:** expand test coverage and introduce pytest-cov ([57f1d17](https://github.com/velocitylabo/tobira/commit/57f1d17141e07d50aa7a319a59a3023ea782af81))


### Documentation

* add bilingual naming with door emoji to README and GitHub Pages ([946c3d9](https://github.com/velocitylabo/tobira/commit/946c3d9bbeabe9d0ba2852487017642517eb2d1b))


### CI

* add GitHub Actions workflows for Python and JS testing ([1afd80f](https://github.com/velocitylabo/tobira/commit/1afd80f8a5c00c26973498e47bbc0903e852d47d))


### Miscellaneous

* **python:** add mypy type checking ([7b7ae6b](https://github.com/velocitylabo/tobira/commit/7b7ae6b864d5b73bce39406144cc2daa00287e08)), closes [#14](https://github.com/velocitylabo/tobira/issues/14)
