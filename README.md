## High level library for Pytorch

Torchlight is a high level library meant to be what Keras is for Tensorflow and Theano.
It is not meant to micmic the Keras API at 100% but instead to get the best of both
worlds (Pytorch and Keras API). 
For instance if you used Keras train/validation generators, in Torchlight you would
use Pytorch [Dataset](http://pytorch.org/docs/master/data.html#torch.utils.data.Dataset) and
[DataLoader](http://pytorch.org/docs/master/data.html#torch.utils.data.DataLoader).

## Documentation

For now the library has no complete documentation but you can quickly get to know how
it works by looking at the examples in the `examples` folder. This library is still in
pre-alpha and many things may break for now. The only things which will evolve at the same
pace as the library are the examples, they are meant to always be up to date with
the library.