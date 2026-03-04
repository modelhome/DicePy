# to build and run from your local machine:
# docker build -t dicepy-runner:local .
# docker run --rm dicepy-runner:local

FROM python:3.12-slim

WORKDIR /app

ENV MPLBACKEND=Agg

COPY dicepy ./dicepy
COPY runner.py ./

RUN pip install --no-cache-dir -U pip \
	&& pip install --no-cache-dir numpy numba matplotlib seaborn scipy pandas

# Pre-warm the Numba JIT cache so first run isn't slow.
RUN python -c "\
import sys; sys.path.insert(0, 'dicepy'); \
from dice_dynamics import objFn, simulateDynamics; \
print('Numba cache warmed')"

ENTRYPOINT ["python", "runner.py"]
