from __future__ import print_function
import timeit
import inspect
import sys
import csv

import lasagne
import numpy as np
import matplotlib.pyplot as plt
import os
import theano
import theano.tensor as T
import cPickle as pickle
import gzip
import pdb

from utils import *
from lasagne.layers import InputLayer, DropoutLayer
from lasagne.layers import DenseLayer
from lasagne.regularization import regularize_network_params, l2

from hw3_cnn import *
from model import *
from all_cnn import *
from conv_pool import *
from strided_cnn import *

def gradient_descend_momentum(cost, params, lr, m):
    updates = []
    for param in params:
        param_update = theano.shared(param.get_value()*0.,broadcastable=param.broadcastable)
        updates.append((param,param-lr*param_update))
        updates.append((param_update,m*param_update+T.grad(cost,param)))
    return updates

def load_model_values(filename):
    with gzip.open(filename, 'rb') as f:
        values = pickle.load(f)
        return values

def save_model(output_layer, filename="model.pklz"):
    values = lasagne.layers.get_all_param_values(output_layer, trainable=True)
    with gzip.open(filename, 'wb') as f:
        pickle.dump(values, f, protocol=2)

def train(model, batch_size = 200, learning_rate=0.1):
    np.random.seed(5468)
    net = model()

    x = net['input'].input_var
    y = T.ivector('y')

    print("........ building model")
    prediction = lasagne.layers.get_output(net['output'],x)

    train_prediction = lasagne.layers.get_output(net['output'], x, deterministic=False)
    test_prediction = lasagne.layers.get_output(net['output'], x, deterministic=True)
    global_avg = lasagne.layers.get_output(net['global_avg'],x)
    before_avg = lasagne.layers.get_output(net['conv7_1'],x)

    lamda = 0.001
    l2_penalty = regularize_network_params(net['output'], l2)

    loss = lasagne.objectives.categorical_crossentropy(train_prediction, y)
    loss_train = lasagne.objectives.aggregate(loss, mode='mean') + lamda*l2_penalty

    test_loss = lasagne.objectives.categorical_crossentropy(test_prediction, y)
    loss_test = lasagne.objectives.aggregate(test_loss, mode='mean')


    params = lasagne.layers.get_all_params(net['output'], trainable=True)


    lr_theano = T.fscalar()

    updates = lasagne.updates.momentum(loss_train, params, momentum=np.float32(0.9), learning_rate=lr_theano)
#     updates = gradient_descend_momentum(cost=loss_train, params=params, lr=lr_theano, m=np.float32(0.9))

    lr_epochs = [200,250, 300]

    y_pred = T.argmax(test_prediction, axis=1)
    errors = T.mean(T.neq(y_pred, y))

    test_prediction_fn = theano.function(inputs=[x], outputs=test_prediction)

    index = T.iscalar()


    # Load Dataset
    train_x, train_y, test_x, test_y = load_cifar_whitened()
    valid_x, valid_y = test_x, test_y

    n_train_batches = train_x.get_value(borrow=True).shape[0] // batch_size
    n_valid_batches = valid_x.get_value(borrow=True).shape[0] // batch_size
    n_test_batches = test_x.get_value(borrow=True).shape[0] // batch_size
    
    train_model = theano.function(inputs=[index, lr_theano], outputs=[loss_train], updates=updates,
            givens={
                x: train_x[index*batch_size:(index+1)*batch_size],
                y: train_y[index*batch_size:(index+1)*batch_size]
                })

    validate_model = theano.function(inputs=[index], outputs=[errors],
            givens={
                x: valid_x[index*batch_size:(index+1)*batch_size],
                y: valid_y[index*batch_size:(index+1)*batch_size]
                })

    test_model = theano.function(inputs=[index], outputs=[errors],
            givens={
                x: test_x[index*batch_size:(index+1)*batch_size],
                y: test_y[index*batch_size:(index+1)*batch_size]
                })
    get_pred = theano.function(inputs=[index], outputs=[y_pred],
            givens={
                x: test_x[index*batch_size:(index+1)*batch_size]
                })
   

    global_avg_fn = theano.function(inputs=[index], outputs=[global_avg],
            givens={
                x: train_x[index*batch_size:(index+1)*batch_size]
                })

    before_avg_fn = theano.function(inputs=[index], outputs=[before_avg],
            givens={
                x: train_x[index*batch_size:(index+1)*batch_size]
                })

    print("........ training")
    model_name = model.__name__
    n_epochs=350
    lr_epochs=[200, 250, 300]
    verbose = True
    lr = learning_rate
    """
    Wrapper function for training and test THEANO model

    :type train_model: Theano.function
    :param train_model:

    :type validate_model: Theano.function
    :param validate_model:

    :type test_model: Theano.function
    :param test_model:

    :type n_train_batches: int
    :param n_train_batches: number of training batches

    :type n_valid_batches: int
    :param n_valid_batches: number of validation batches

    :type n_test_batches: int
    :param n_test_batches: number of testing batches

    :type n_epochs: int
    :param n_epochs: maximal number of epochs to run the optimizer

    :type verbose: boolean
    :param verbose: to print out epoch summary or not to

    """

    # early-stopping parameters
    patience = 100000  # look as this many examples regardless
    patience_increase = 2  # wait this much longer when a new best is
                           # found
    improvement_threshold = 0.9995  # a relative improvement of this much is
                                   # considered significant
    validation_frequency = min(n_train_batches, patience // 2)
                                  # go through this many
                                  # minibatche before checking the network
                                  # on the validation set; in this case we
                                  # check every epoch

    best_validation_loss = np.inf
    best_iter = 0
    test_score = 0.
    start_time = timeit.default_timer()

    epoch = 0
    best_epoch = 0
    done_looping = False

    curframe = inspect.currentframe()
    calframe = inspect.getouterframes(curframe, 2)

    while (epoch < n_epochs) and (not done_looping):
        if epoch % 50 == 0  or epoch in lr_epochs:
            save_model(net['output'], "{0}_{1}.pklz".format(model_name, epoch))
        if epoch in lr_epochs:
            lr *= 0.1
        epoch = epoch + 1
        
        for minibatch_index in range(n_train_batches):

            iter = (epoch - 1) * n_train_batches + minibatch_index

            if (iter % 100 == 0) and verbose:
                print('training @ iter = ', iter, file=sys.stderr)
            
            cost_ij = train_model(minibatch_index, lr)

            if (iter + 1) % validation_frequency == 0:

                # compute zero-one loss on validation set
                validation_losses = [validate_model(i) for i
                                     in range(n_valid_batches)]
      
                this_validation_loss = np.mean(validation_losses)

                if verbose:
                    print('epoch %i, loss %f, minibatch %i/%i, validation error %f %%' %
                        (epoch,
                        cost_ij[0],
                         minibatch_index + 1,
                         n_train_batches,
                         this_validation_loss * 100.), file=sys.stderr)

                # if we got the best validation score until now
                if this_validation_loss < best_validation_loss:

                    best_epoch = epoch
                    #improve patience if loss improvement is good enough
                    if this_validation_loss < best_validation_loss *  \
                       improvement_threshold:
                        patience = max(patience, iter * patience_increase)

                    # save best validation score and iteration number
                    best_validation_loss = this_validation_loss
                    best_iter = iter

                    # test it on the test set
                    test_losses = [
                        test_model(i)
                        for i in range(n_test_batches)
                    ]
                    test_score = np.mean(test_losses)

                    if verbose:
                        csvfile = open(model_name + '_results.csv', 'a')
                        resultswriter = csv.writer(csvfile)
                        print(('     epoch %i, minibatch %i/%i, test error of '
                               'best model %f %%') %
                              (epoch, minibatch_index + 1,
                               n_train_batches,
                               test_score * 100.), file=sys.stderr)
                        resultswriter.writerow([best_validation_loss, epoch, best_iter, n_train_batches, test_score, model_name, learning_rate])
                        csvfile.close()

            if patience <= iter or (best_validation_loss == 0.0 and test_score == 0.0):
                done_looping = True
                break

    end_time = timeit.default_timer()

    # Retrieve the name of function who invokes train_nn() (caller's name)

    # Print out summary
    print('Optimization complete.')
    print('Best validation score of %f %% obtained at iteration %i, '
          'with test performance %f %%' %
          (best_validation_loss * 100., best_iter + 1, test_score * 100.))
    print(('The training process for function ' +
           calframe[1][3] +
           ' ran for %.2fm' % ((end_time - start_time) / 60.)))
    # Retrieve the name of function who invokes train_nn() (caller's name)

if __name__ == "__main__":
    lr = 0.25
    lr = float(sys.argv[2])
    mod_id = sys.argv[1]
    d = {}
    d['hw3_cnn'] = hw3_cnn
    d['model_a'] = model_a
    d['model_b'] = model_b
    d['model_c'] = model_c
    d['all_cnn_a'] = all_cnn_a
    d['all_cnn_b'] = all_cnn_b
    d['all_cnn_c'] = all_cnn_c
    d['conv_pool_cnn_a'] = conv_pool_cnn_a
    d['conv_pool_cnn_b'] = conv_pool_cnn_b
    d['conv_pool_cnn_c'] = conv_pool_cnn_c
    d['strided_cnn_a'] = strided_cnn_a
    d['strided_cnn_b'] = strided_cnn_b
    d['strided_cnn_c'] = strided_cnn_c
    print ('learning rate: ' + str(lr))
    print ('model: '+mod_id)
    model = d[mod_id]
    train(model, learning_rate=lr)
