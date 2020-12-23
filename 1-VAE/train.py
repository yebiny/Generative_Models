import tensorflow as tf
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from models import *
from drawTools import *

def reduce_lr(pre_v_loss, v_loss, count, lr, patience, factor, min_lr):
    if v_loss < pre_v_loss:
        count = 0
    else:
        count += 1
        if count >= patience:
            lr = lr*factor
            if lr < min_lr:
                lr = min_lr
            count = 0
            print('reduce learning rate..', lr)
    return count, lr


class TrainVAE():

    def __init__(self, x_train, x_valid, save_path, latent_dim=100, ckp='y'):
        self.x_train = x_train
        self.x_valid = x_valid
       
        encoder, decoder, vae = build_vae(x_train.shape, latent_dim)
        self.encoder = encoder
        self.decoder = decoder
        self.vae = vae
       
        self.save_path = save_path
        self.ckp_dir = self.save_path+'/ckp/'

        self.checkpoint = tf.train.Checkpoint(step=tf.Variable(1), encoder=self.encoder, decoder=self.decoder, vae=self.vae)
        if ckp=='y':
            self.checkpoint.restore(tf.train.latest_checkpoint(self.ckp_dir))

    def get_rec_loss(self, inputs, predictions):
        rec_loss = tf.keras.losses.binary_crossentropy(inputs, predictions)
        rec_loss = tf.reduce_mean(rec_loss)
        rec_loss *= self.x_train.shape[1]*self.x_train.shape[2]
        return rec_loss
    
    def get_kl_loss(self, z_log_var, z_mean):
        kl_loss = 1 + z_log_var - K.square(z_mean) - K.exp(z_log_var)
        kl_loss = tf.reduce_mean(kl_loss)
        kl_loss *= -0.5
        return kl_loss
  
    @tf.function
    def train_step(self, inputs, train_loss, optimizer):
        with tf.GradientTape() as tape:
    
            # Get model ouputs
            z_log_var, z_mean, z = self.encoder(inputs)
            predictions = self.decoder(z)
    
            # Compute losses
            rec_loss = self.get_rec_loss(inputs, predictions)
            kl_loss = self.get_kl_loss(z_log_var, z_mean)
            loss = rec_loss + kl_loss
    
        # Compute gradients
        varialbes = self.vae.trainable_variables
        gradients = tape.gradient(loss, varialbes)
        # Update weights
        optimizer.apply_gradients(zip(gradients, varialbes))
    
        # Update train loss
        train_loss(loss)
        
        
    @tf.function
    def valid_step(self, inputs, valid_loss):
        with tf.GradientTape() as tape:

            # Get model ouputs without training
            z_log_var, z_mean, z = self.encoder(inputs, training=False)
            predictions = self.decoder(z, training=False)

            # Compute losses
            rec_loss = self.get_rec_loss(inputs, predictions)
            kl_loss = self.get_kl_loss(z_log_var, z_mean)
            loss = rec_loss + kl_loss

        # Update valid loss 
        valid_loss(loss)

    def make_dataset(self, batch_size):
        train_ds = tf.data.Dataset.from_tensor_slices((self.x_train, self.x_train)).batch(batch_size)
        valid_ds = tf.data.Dataset.from_tensor_slices((self.x_valid, self.x_valid)).batch(batch_size)
        return train_ds, valid_ds


    def train(self, epochs, batch_size=32, init_lr=0.001):
     
        train_ds, valid_ds = self.make_dataset(batch_size) 

        csv_logger = tf.keras.callbacks.CSVLogger(self.save_path+'/training.log')
        optimizer = tf.keras.optimizers.Adam(init_lr)
        train_loss = tf.keras.metrics.Mean(name='train_loss')
        valid_loss = tf.keras.metrics.Mean(name='valid_loss') 
        
        # Initialize values
        best_loss, count = float('inf'), 0
        
        # Start epoch loop
        for epoch in range(epochs):
            
            for inputs, outputs in train_ds:
                self.train_step(inputs, train_loss, optimizer)
            
            for inputs, outputs in valid_ds:
                self.valid_step(inputs, valid_loss)
            
            # Get loss and leraning rate at this epoch
            t_loss = train_loss.result().numpy() 
            v_loss = valid_loss.result().numpy()
            l_rate = optimizer.learning_rate.numpy()
        
            # Control learning rate
            count, lr  = reduce_lr(best_loss, v_loss, count, l_rate, 5, 0.2, 0.00001)
            optimizer.learning_rate = lr
            
            # Plot reconstruct image per 10 epochs
            plot_rec_images(self.vae, self.x_valid[:100], save=self.save_path+'recImg_%i'%epoch)
            
            # Save checkpoint if best v_loss 
            if v_loss < best_loss:
                best_loss = v_loss
                self.checkpoint.save(file_prefix=os.path.join(self.save_path+'/ckp/', 'ckp'))
            
            # Save loss, lerning rate
            print("* %i * loss: %f, v_loss: %f,  best_loss: %f, l_rate: %f, lr_count: %i"%(epoch, t_loss, v_loss, best_loss, l_rate, count ))
            df = pd.DataFrame({'epoch':[epoch], 'loss':[t_loss], 'v_loss':[v_loss], 'best_loss':[best_loss], 'l_rate':[l_rate]  } )
            df.to_csv(self.save_path+'/process.csv', mode='a', header=False)
            
    
            # Reset loss
            train_loss.reset_states()   
            valid_loss.reset_states()
           
     