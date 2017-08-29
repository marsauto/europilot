# EuroPilot

## Overview
<div align = 'center'>
	<img src = 'examples/day.gif' width='280'>
	<img src = 'examples/night.gif' width='280'>
</div>

EuroPilot is an open source project that leverages the popular Euro Truck Simulator(ETS2) to develop self driving algorithms. Think of EuroPilot as a bridge between the game environment, and your favorite deep-learning framework, such as Keras or Tensorflow. With EuroPilot, you can capture the game screen input, and programatically control the truck inside the simulator. 

EuroPilot can be used in one of two ways: training or testing. 

For training, EuroPliot can capture the screen input and ouput a numpy array in realtime, while simultaenously getting the wheel-joystick values. The mapping between the relevant screenshot and the joystick values is written inside a csv file.
<div align = 'center'>
	<img src = 'examples/example_csv.png'>
</div>
<p align = 'center'>
In the csv file, each row has the screenshot filename with the joystick values. 
</p>

For testing, EuroPilot can create a virtual joystick driver that can be recognized inside the game, which can be used to programatically control the truck. Using this joystick, you can create a real-time inference network that uses the game screen as the input, and outputs the relevant joystick commands, such as steering. 

[Click to see an example demo on YouTube.](https://www.youtube.com/watch?v=n2pPR3WLaxI)

## Getting Started

First, clone the project

```
git clone https://github.com/marshq/europilot
```

Install prerequisite libraries

Add training instructions

For running inference on the model, check out [inference.ipynb](scripts/inference.ipynb) in the scripts directory.

## General Architecture

쓸까말까...

## Why Euro Truck Simulator 2?

Europilot captures the screen input, therefore technically it is game agnostic. We chose ETS2 as our first target for several reasons.

* Multi platform support: ETS2 supports Windows, OS X, and Linux. Developers can run the game in a Macbook, or in a Ubuntu workstation. This put ETS2 ahead of games such as GTAV.


* Realistic graphics/physics: We looked at open source games, but found that the graphics or physics engine was not realistic enough for our use case. ETS2 afterall, has "simulator" inside its title.


* Fun: Having a large dataset is critical to developing a good model. Therefore you, as a developer, have to play many hours of whatever game you target. Fortunately, ETS2 is fun to play!


## Running the tests

Explain how to run the automated tests for this system

### Break down into end to end tests

Explain what these tests test and why

```
Give an example
```

### And coding style tests

Explain what these tests test and why

```
Give an example
```

## License

This project is licensed under the MIT License.