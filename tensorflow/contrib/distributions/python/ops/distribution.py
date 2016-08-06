# Copyright 2016 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Base classes for probability distributions."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import abc
import six

from tensorflow.python.framework import dtypes
from tensorflow.python.framework import ops
from tensorflow.python.framework import tensor_util
from tensorflow.python.ops import array_ops
from tensorflow.python.ops import math_ops


@six.add_metaclass(abc.ABCMeta)
class BaseDistribution(object):
  """Simple abstract base class for probability distributions.

  Implementations of core distributions to be included in the `distributions`
  module should subclass `Distribution`. This base class may be useful to users
  that want to fulfill a simpler distribution contract.
  """

  @abc.abstractproperty
  def name(self):
    """Name to prepend to all ops."""
    # return self._name.
    pass

  @abc.abstractmethod
  def prob(self, value, name="prob"):
    """Probability density/mass function."""
    with ops.name_scope(self.name):
      with ops.op_scope([value], name):
        value = ops.convert_to_tensor(value)
        return math_ops.exp(self.log_prob(value))

  @abc.abstractmethod
  def log_prob(self, value, name="log_prob"):
    """Log of the probability density/mass function."""
    with ops.name_scope(self.name):
      with ops.op_scope([value], name):
        value = ops.convert_to_tensor(value)
        return math_ops.log(self.prob(value))

  def sample_n(self, n, seed=None, name="sample_n"):
    """Generate `n` samples.

    Args:
      n: scalar. Number of samples to draw.
      seed: Python integer seed for RNG
      name: name to give to the op.

    Returns:
      samples: a `Tensor` with a prepended dimension (n,).
    """
    raise NotImplementedError("sample_n not implemented")

  def sample(self, sample_shape=(), seed=None, name="sample"):
    """Generate samples of the specified shape.

    Note that a call to `sample()` without arguments will generate a single
    sample.

    Args:
      sample_shape: Rank 1 `int32` `Tensor`. Shape of the generated samples.
      seed: Python integer seed for RNG
      name: name to give to the op.

    Returns:
      samples: a `Tensor` with prepended dimensions `sample_shape`.
    """
    with ops.name_scope(self.name):
      with ops.op_scope([sample_shape], name):
        sample_shape = ops.convert_to_tensor(sample_shape,
                                             dtype=dtypes.int32,
                                             name="sample_shape")
        total = math_ops.reduce_prod(sample_shape)
        samples = self.sample_n(total, seed)
        output_shape = array_ops.concat(0, [sample_shape, array_ops.slice(
            array_ops.shape(samples), [1], [-1])])
        output = array_ops.reshape(samples, output_shape, name=name)
        output.set_shape(tensor_util.constant_value_as_shape(
            sample_shape).concatenate(samples.get_shape()[1:]))
    return output


@six.add_metaclass(abc.ABCMeta)
class Distribution(BaseDistribution):
  """Fully-featured abstract base class for probability distributions.

  This class defines the API for probability distributions. Users will only ever
  instantiate subclasses of `Distribution`.

  ### API

  The key methods for probability distributions are defined here.

  To keep ops generated by the distribution tied together by name, subclasses
  should override `name` and use it to prepend names of ops in other methods
  (see `cdf` for an example).

  Subclasses that wish to support `cdf` and `log_cdf` can override `log_cdf`
  and use the base class's implementation for `cdf`, or vice versa. The same
  goes for `log_prob` and `prob`.

  ### Broadcasting, batching, and shapes

  All distributions support batches of independent distributions of that type.
  The batch shape is determined by broadcasting together the parameters.

  The shape of arguments to `__init__`, `cdf`, `log_cdf`, `prob`, and
  `log_prob` reflect this broadcasting, as does the return value of `sample` and
  `sample_n`.

  `sample_n_shape = (n,) + batch_shape + event_shape`, where `sample_n_shape` is
  the shape of the `Tensor` returned from `sample_n`, `n` is the number of
  samples, `batch_shape` defines how many independent distributions there are,
  and `event_shape` defines the shape of samples from each of those independent
  distributions. Samples are independent along the `batch_shape` dimensions, but
  not necessarily so along the `event_shape` dimensions (dependending on the
  particulars of the underlying distribution).

  Using the `Uniform` distribution as an example:

  ```python
  minval = 3.0
  maxval = [[4.0, 6.0],
            [10.0, 12.0]]

  # Broadcasting:
  # This instance represents 4 Uniform distributions. Each has a lower bound at
  # 3.0 as the `minval` parameter was broadcasted to match `maxval`'s shape.
  u = Uniform(minval, maxval)

  # `event_shape` is `TensorShape([])`.
  event_shape = u.get_event_shape()
  # `event_shape_t` is a `Tensor` which will evaluate to [].
  event_shape_t = u.event_shape

  # Sampling returns a sample per distribution.  `samples` has shape
  # (5, 2, 2), which is (n,) + batch_shape + event_shape, where n=5,
  # batch_shape=(2, 2), and event_shape=().
  samples = u.sample_n(5)

  # The broadcasting holds across methods. Here we use `cdf` as an example. The
  # same holds for `log_cdf` and the likelihood functions.

  # `cum_prob` has shape (2, 2) as the `value` argument was broadcasted to the
  # shape of the `Uniform` instance.
  cum_prob_broadcast = u.cdf(4.0)

  # `cum_prob`'s shape is (2, 2), one per distribution. No broadcasting
  # occurred.
  cum_prob_per_dist = u.cdf([[4.0, 5.0],
                             [6.0, 7.0]])

  # INVALID as the `value` argument is not broadcastable to the distribution's
  # shape.
  cum_prob_invalid = u.cdf([4.0, 5.0, 6.0])

  ### Parameter values leading to undefined statistics or distributions.

  Some distributions do not have well-defined statistics for all initialization
  parameter values.  For example, the beta distribution is parameterized by
  positive real numbers `a` and `b`, and does not have well-defined mode if
  `a < 1` or `b < 1`.

  The user is given the option of raising an exception or returning `NaN`.

  ```python
  a = tf.exp(tf.matmul(logits, weights_a))
  b = tf.exp(tf.matmul(logits, weights_b))

  # Will raise exception if ANY batch member has a < 1 or b < 1.
  dist = distributions.beta(a, b, allow_nan_stats=False)  # default is False
  mode = dist.mode().eval()

  # Will return NaN for batch members with either a < 1 or b < 1.
  dist = distributions.beta(a, b, allow_nan_stats=True)
  mode = dist.mode().eval()
  ```

  In all cases, an exception is raised if *invalid* parameters are passed, e.g.

  ```python
  # Will raise an exception if any Op is run.
  negative_a = -1.0 * a  # beta distribution by definition has a > 0.
  dist = distributions.beta(negative_a, b, allow_nan_stats=True)
  dist.mean().eval()
  ```

  """

  @abc.abstractproperty
  def allow_nan_stats(self):
    """Boolean describing behavior when a stat is undefined for batch member."""
    # return self._allow_nan_stats
    # Notes:
    #
    # When it makes sense, return +- infinity for statistics.  E.g. the variance
    # of a Cauchy distribution would be +infinity.  However, sometimes the
    # statistic is undefined (e.g. if a distribution's pdf does not achieve a
    # maximum within the support of the distribution, mode is undefined).
    # If the mean is undefined, then by definition the variance is undefined.
    # E.g. the mean for Student's T for df = 1 is undefined (no clear way to say
    # it is either + or - infinity), so the variance = E[(X - mean)^2] is also
    # undefined.
    #
    # Distributions should be initialized with a kwarg "allow_nan_stats" with
    # the following docstring (refer to above docstring note on undefined
    # statistics for more detail).
    # allow_nan_stats:  Boolean, default False.  If False, raise an exception if
    #   a statistic (e.g. mean/mode/etc...) is undefined for any batch member.
    #   If True, batch members with valid parameters leading to undefined
    #   statistics will return NaN for this statistic.
    pass

  @abc.abstractproperty
  def validate_args(self):
    """Boolean describing behavior on invalid input."""
    # return self._validate_args.
    pass

  @abc.abstractproperty
  def dtype(self):
    """dtype of samples from this distribution."""
    # return self._dtype
    pass

  @abc.abstractmethod
  def event_shape(self, name="event_shape"):
    """Shape of a sample from a single distribution as a 1-D int32 `Tensor`.

    Args:
      name: name to give to the op

    Returns:
      `Tensor` `event_shape`
    """
    # For scalar distributions, constant([], int32)
    # with ops.name_scope(self.name):
    #   with ops.op_scope([tensor_arguments], name):
    #     Your code here
    pass

  @abc.abstractmethod
  def get_event_shape(self):
    """`TensorShape` available at graph construction time.

    Same meaning as `event_shape`. May be only partially defined.
    """
    # return self._event_shape
    pass

  @abc.abstractmethod
  def batch_shape(self, name="batch_shape"):
    """Batch dimensions of this instance as a 1-D int32 `Tensor`.

    The product of the dimensions of the `batch_shape` is the number of
    independent distributions of this kind the instance represents.

    Args:
      name: name to give to the op

    Returns:
      `Tensor` `batch_shape`
    """
    # with ops.name_scope(self.name):
    #   with ops.op_scope([tensor_arguments], name):
    #     Your code here
    pass

  @abc.abstractmethod
  def get_batch_shape(self):
    """`TensorShape` available at graph construction time.

    Same meaning as `batch_shape`. May be only partially defined.
    """
    pass

  def sample_n(self, n, seed=None, name="sample_n"):
    """Generate `n` samples.

    Args:
      n: scalar. Number of samples to draw from each distribution.
      seed: Python integer seed for RNG
      name: name to give to the op.

    Returns:
      samples: a `Tensor` of shape `(n,) + self.batch_shape + self.event_shape`
          with values of type `self.dtype`.
    """
    return super(Distribution, self).sample_n(n, seed, name)

  def sample(self, sample_shape=(), seed=None, name="sample"):
    """Generate samples of the specified shape for each batched distribution.

    Note that a call to `sample()` without arguments will generate a single
    sample per batched distribution.

    Args:
      sample_shape: Rank 1 `int32` `Tensor`. Shape of the generated samples.
      seed: Python integer seed for RNG
      name: name to give to the op.

    Returns:
      samples: a `Tensor` of dtype `self.dtype` and shape
          `sample_shape + self.batch_shape + self.event_shape`.
    """
    return super(Distribution, self).sample(sample_shape, seed, name)

  def cdf(self, value, name="cdf"):
    """Cumulative distribution function."""
    with ops.name_scope(self.name):
      with ops.op_scope([value], name):
        value = ops.convert_to_tensor(value)
        return math_ops.exp(self.log_cdf(value))

  def log_cdf(self, value, name="log_cdf"):
    """Log CDF."""
    raise NotImplementedError("log_cdf is not implemented")

  def entropy(self, name="entropy"):
    """Entropy of the distribution in nats."""
    raise NotImplementedError("entropy not implemented")

  def mean(self, name="mean"):
    """Mean of the distribution."""
    raise NotImplementedError("mean not implemented")

  def mode(self, name="mode"):
    """Mode of the distribution."""
    raise NotImplementedError("mode not implemented")

  def std(self, name="std"):
    """Standard deviation of the distribution."""
    raise NotImplementedError("std not implemented")

  def variance(self, name="variance"):
    """Variance of the distribution."""
    raise NotImplementedError("variance not implemented")

  @abc.abstractproperty
  def is_continuous(self):
    pass

  @abc.abstractproperty
  def is_reparameterized(self):
    pass

  def log_pdf(self, value, name="log_pdf"):
    """Log of the probability density function."""
    if self.is_continuous:
      return self.log_prob(value, name=name)
    else:
      raise NotImplementedError(
          "log_pdf is not implemented for non-continuous distributions")

  def pdf(self, value, name="pdf"):
    """The probability density function."""
    if self.is_continuous:
      return self.prob(value, name=name)
    else:
      raise NotImplementedError(
          "pdf is not implemented for non-continuous distributions")

  def log_pmf(self, value, name="log_pmf"):
    """Log of the probability mass function."""
    if self.is_continuous:
      raise NotImplementedError(
          "log_pmf is not implemented for continuous distributions")
    else:
      return self.log_prob(value, name=name)

  def pmf(self, value, name="pmf"):
    """The probability mass function."""
    if self.is_continuous:
      raise NotImplementedError(
          "pmf is not implemented for continuous distributions")
    else:
      return self.prob(value, name=name)
