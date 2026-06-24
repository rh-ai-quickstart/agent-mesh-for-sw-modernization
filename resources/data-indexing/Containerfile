FROM quay.io/modh/odh-generic-data-science-notebook@sha256:7c1a4ca213b71d342a2d1366171304e469da06d5f15710fab5dd3ce013aa1b73

USER 1001

COPY requirements.txt ./requirements.txt

RUN pip install --upgrade pip \
	&& pip install -r requirements.txt