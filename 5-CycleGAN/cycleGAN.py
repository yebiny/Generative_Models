import tensorflow as tf
from tensorflow.keras import layers, models
from tensorflow.keras.utils import plot_model
import numpy as np
import os, sys, pickle
import matplotlib.pyplot as plt



class CycleGAN():
    def __init__(self, generator_ab, generator_ba, discriminator_a, discriminator_b):
       
        # set init vars
        self.name = 'cycleGAN'
        self.gene_ab = generator_ab
        self.gene_ba = generator_ba
        self.disc_a = discriminator_a
        self.disc_b = discriminator_b
        self.input_shape = discriminator_a.input_shape[1:]

    def compile( self
               , optimizer 
               , lambda_valid = 1 
               , lambda_cycle = 10
               , lambda_ident = 9 ):
        
        
        self.disc_a.compile(loss='mse', optimizer=optimizer, metrics=['accuracy'])
        self.disc_b.compile(loss='mse', optimizer=optimizer, metrics=['accuracy'])
        
        self.disc_a.trainable=False
        self.disc_b.trainable=False

        img_a = layers.Input(shape = self.input_shape, name='input_a')
        img_b = layers.Input(shape = self.input_shape, name='input_b')
        
        fake_b = self.gene_ab(img_a)
        fake_a = self.gene_ba(img_b)
        
        reco_b = self.gene_ab(fake_a)
        reco_a = self.gene_ba(fake_b)
        
        cycle_b = self.gene_ab(img_b)
        cycle_a = self.gene_ba(img_a)
       
        valid_a = self.disc_a(fake_a)
        valid_b = self.disc_b(fake_b)
        
        self.cyclegan = models.Model(name='CycleGAN',
                                inputs=[img_a, img_b], 
                                outputs=[valid_a, valid_b, 
                                        reco_a, reco_b,
                                        cycle_a, cycle_b])

        self.cyclegan.compile(loss = ['mse', 'mse', 'mae', 'mae', 'mae', 'mae'],
                              loss_weights=[lambda_valid, lambda_valid, 
                                            lambda_cycle, lambda_cycle, 
                                            lambda_ident, lambda_ident],
                              optimizer=optimizer) 
        
        self.disc_a.trainable=True
        self.disc_b.trainable=True


    def _make_datasets(self, x_data, batch_size):
        dataset = tf.data.Dataset.from_tensor_slices(x_data).shuffle(1)
        dataset = dataset.batch(batch_size, drop_remainder=True).prefetch(1)
        return dataset
    
    def _make_constant(self, batch_size):
        patch=int(self.input_shape[0]/2**4)
        disc_patch = (patch, patch, 1)
        y1 = np.ones((batch_size, ) + disc_patch)
        y0 = np.zeros((batch_size, ) +disc_patch)
        return y0, y1
        
    def train(self, train_a, train_b, epochs, batch_size, iterval=10):
        
        # set data
        dataset_a = self._make_datasets(train_a, batch_size)
        dataset_b = self._make_datasets(train_b, batch_size)
        # set constant 
        y0, y1 = self._make_constant(batch_size)
        
        # train
        history = {'d_loss':[], 'g_loss':[]}
        self.plot_sample_images(train_a, self.gene_ab, save_name='results/img_ab_0')
        self.plot_sample_images(train_b, self.gene_ba, save_name='results/img_ba_0')
        for epoch in range(1, epochs+1):
            print("* epoch {}/{}".format(epoch, epochs))
            
            gene_loss, disc_loss = 0,0
            for imgs_a, imgs_b in zip (dataset_a, dataset_b):
            
                fake_b = self.gene_ab.predict(imgs_a)
                fake_a = self.gene_ba.predict(imgs_b)
                
                self.disc_a.trainable = True
                self.disc_b.trainable = True
                
                da_loss_real = self.disc_a.train_on_batch(imgs_a, y1)
                da_loss_fake = self.disc_a.train_on_batch(fake_a, y0)
                da_loss = 0.5*np.add(da_loss_real, da_loss_fake)

                db_loss_real = self.disc_b.train_on_batch(imgs_b, y1)
                db_loss_fake = self.disc_b.train_on_batch(fake_b, y0)
                db_loss = 0.5*np.add(db_loss_real, db_loss_fake)
                
                d_loss = 0.5*np.add(da_loss, db_loss)
                
                self.disc_a.trainable = False
                self.disc_b.trainable = False
                g_loss = self.cyclegan.train_on_batch([imgs_a, imgs_b],
                                                     [y1, y1, imgs_a, imgs_b, imgs_a, imgs_b]) 
                
                disc_loss = disc_loss + d_loss[0]
                gene_loss = gene_loss + g_loss[0]
                
            history['d_loss'].append(disc_loss)
            history['g_loss'].append(gene_loss)
            
            self.plot_sample_images(train_a, self.gene_ab, save_name='results/img_ab_%i'%epoch)
            self.plot_sample_images(train_b, self.gene_ba, save_name='results/img_ba_%i'%epoch)
        
        return history

    def plot_sample_images(self, img, generator, save_name=None):
        r, c = 5, 5
        gen_imgs = generator.predict(img[:r*c])

        #Rescale images 0 - 1
        gen_imgs = 0.5 * (gen_imgs + 1)
        gen_imgs = np.clip(gen_imgs, 0, 1)

        fig, axs = plt.subplots(r, c, figsize=(15,15))
        cnt = 0

        for i in range(r):
            for j in range(c):
                axs[i,j].imshow(np.squeeze(gen_imgs[cnt, :,:,:]), cmap = 'gray_r')
                axs[i,j].axis('off')
                cnt += 1
        
        if save_name==None:
            plt.show()
        else:
            fig.savefig(save_name)
            plt.close()

    def plot_model(self, save_path):
        plot_model(self.cyclegan, to_file='%s/cyclegan.png'%save_path, show_shapes = True, show_layer_names = True)
        plot_model(self.gene_ab, to_file='%s/generator.png'%save_path, show_shapes = True, show_layer_names = True)
        plot_model(self.disc_a, to_file='%s/discriminator.png'%save_path, show_shapes = True, show_layer_names = True)

    def save_model(self, save_path):
        self.cyclegan.save('%s/cyclegan.h5'%save_path)
        self.gene_ab.save('%s/generator_ab.h5'%save_path)
        self.gene_ba.save('%s/generator_ba.h5'%save_path)
        self.disc_a.save('%s/discriminator_a.h5'%save_path)
        self.disc_b.save('%s/discriminator_b.h5'%save_path)
